import os
import json
import signal
import threading
import contextlib
from typing import Union
from datetime import datetime
from json import JSONDecodeError
from urllib.request import urlopen, Request, HTTPError

import sentry_sdk
from slack_bolt import App
from cachetools import cached, TTLCache
from slack_bolt.adapter.socket_mode import SocketModeHandler

from middleware.laas import jira_summary_generator
from middleware.laas.heuristic import outside_slack_jira_user_map
from middleware.laas.jira_operator import JiraOperator
from middleware.laas.jira_fields_schema import Issue, get_format_instructions

if os.getenv('DEBUG', False):
    from dotenv import load_dotenv
    load_dotenv()

# Initializes your app with your bot token and socket mode handler
app = App(token=os.environ['SLACK_BOT_TOKEN'])
slack_handler = SocketModeHandler(app_token=os.environ['SLACK_APP_TOKEN'], app=app)


class SlackCollection:
    # FIXME:
    workspace = 'wantedx.slack.com'
    loading_emoji = 'loading'


class PIThreadAll:
    # FIXME:
    workspace = 'wantedlab.atlassian.net'
    project = 'PI'
    trigger_emoji = 'pi_jira_gen'
    laas_jira_hash = '7d7e1e4c2652e5c82b29e9dd88a7630a1e0f004b4cd971314b8126e4f16aab1c'
    is_root: bool = True


class PIThreadItem:
    workspace = 'wantedlab.atlassian.net'
    project = 'PI'
    trigger_emoji = 'pi_thread'
    laas_jira_hash = '7d7e1e4c2652e5c82b29e9dd88a7630a1e0f004b4cd971314b8126e4f16aab1c'
    is_root: bool = False


class SlackOperator:
    def __init__(self, event, say, trigger_emoji):
        self.event = event
        self.say = say

        self.item_ts = event['item']['ts']
        self.item_channel = event['item']['channel']
        self.item_user = event['item_user']
        self.reaction_user = event['user']
        self.emoji = trigger_emoji

        # after get_conversation_data
        self.thread_ts = None
        self.context = None
        self.screenshots = None

        self.user_map = {
            x['id']: {'real_name': x['real_name'], 'email': x['profile'].get('email')}
            for x in get_all_slack_user_list() if not x['deleted']
        }

    def get_conversation_data(self, root=True):
        """
        스레드의 모든 메시지를 가져와 정제합니다
        """
        context = ''
        screenshots = []
        conversations = app.client.conversations_replies(
            channel=self.item_channel,
            ts=self.item_ts,
        )
        self.thread_ts = conversations["messages"][0].get("thread_ts")
        if root and self.thread_ts and self.thread_ts != self.item_ts:
            self.say(
                channel=self.reaction_user,
                blocks=[
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f'스레드 최상단에 이모지를 달아주세요.'
                        },
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f':{self.emoji}: 이모지가 스레드 내부에 달려있어서 지라 이슈를 생성할 수 없습니다. 스레드 최상단에 이모지를 달아주세요.',
                            },
                        ]
                    }
                ],
            )
            return False

        # 모든 대화 메시지를 가져옵니다
        for message in conversations["messages"]:
            # Process each message in the thread
            message_dt = datetime.fromtimestamp(float(message['ts'])).isoformat()
            user_name = self.user_map.get(message['user'], {'real_name': 'Unknown'})['real_name']
            text = message.get("text", "")
            context += f'{message_dt} {user_name}: """{text}"""' + '\n\n'

            # conversation 에 대한 모든 첨부파일을 복제합니다.
            for file in message.get('files', []):
                private_file_url = file['url_private']
                headers = {'Authorization': f'Bearer {os.environ["SLACK_BOT_TOKEN"]}'}
                req = Request(private_file_url, headers=headers)
                try:
                    response = urlopen(req)
                except HTTPError:
                    continue
                content = response.read()
                screenshots.append(content)

        self.context = context
        self.screenshots = screenshots
        return True

    @property
    def link(self):
        return f'https://{SlackCollection.workspace}/archives/{self.item_channel}/p{self.item_ts.replace(".", "")}{f"?thread_ts={self.thread_ts}" if self.thread_ts else ""}'

    def check_gpt_response(self, hash, params):
        """
        GPT 응답이 올바른지 확인합니다.
        이 단계는 LaaS 서버의 응답을 잘 받았는지 확인하는 단계입니다
        """
        try:
            gpt_response = jira_summary_generator(hash, params)
        except Exception as e:
            self.say(
                channel=self.reaction_user,
                blocks=[
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f'LaaS 서버에 요청하는 도중에 실패했습니다. 잠시 후 다시 시도해주세요. 동일한 문제가 계속 발생하면 관리자에게 문의해주세요.'
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f'Error Message: ```{e}``',
                            },
                            {
                                "type": "mrkdwn",
                                "text": f'<{self.link}|스레드 바로가기>',
                            }
                        ]
                    }
                ],
            )
            raise e
        try:
            return gpt_response.json()['choices'][0]['message']['content']
        except KeyError as e:
            self.say(
                channel=self.reaction_user,
                blocks=[
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f'Jira 이슈 생성에 실패했습니다.'
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f'너무 많은 글자수가 스레드에 있진 않은지 확인해 보세요.\nError Message: ```{gpt_response}```',
                            },
                            {
                                "type": "mrkdwn",
                                "text": f'<{self.link}|스레드 바로가기>',
                            }
                        ]
                    }
                ],
            )
            raise e

    def validate_gpt_response_json(self, gpt_response, say):
        """
        GPT 응답이 올바른 JSON 형식인지 확인합니다.
        이 단계는 요구사항에 맞게 JSON 응답을 받았는지 확인하는 단계입니다
        """
        try:
            gpt_metadata = json.loads(gpt_response)
            assert gpt_metadata['issue_type'] in ['버그', '작업']
            return gpt_metadata
        except AssertionError as e:
            say(
                channel=self.reaction_user,
                blocks=[
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f'Jira 이슈 생성에 실패했습니다.'
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": gpt_response,
                            },
                            {
                                "type": "mrkdwn",
                                "text": f'GPT 분류에 실패했습니다. 지라를 생성하기에 앞서 스레드 요약이 충분한지 확인해보세요.',
                            },
                            {
                                "type": "mrkdwn",
                                "text": f'<{self.link}|스레드 바로가기>',
                            }
                        ]
                    }
                ],
            )
        except JSONDecodeError as e:
            say(
                channel=self.reaction_user,
                blocks=[
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f'Jira 이슈 생성에 실패했습니다.'
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": gpt_response,
                            },
                            {
                                "type": "mrkdwn",
                                "text": f'GPT 가 생성한 내용을 지라로 전달할 수 없어서 실패했습니다. 지라를 생성하기에 앞서 스레드 요약이 충분한지 확인해보세요.',
                            },
                            {
                                "type": "mrkdwn",
                                "text": f'<{self.link}|스레드 바로가기>',
                            }
                        ]
                    }
                ],
            )
            raise e


@cached(cache=TTLCache(maxsize=1, ttl=60 * 60 * 24))
def get_all_slack_user_list():
    return app.client.users_list()['members']


@app.event("team_join")
def onboarding(event, say):
    get_all_slack_user_list.cache_clear()


def check_emoji(event, say, emoji):
    """
    이미 스레드에 이모지, 즉 생성된 이슈가 있는지 확인합니다.
    스레드 내부에 이미 이모지가 있는 경우에는 이슈를 생성하지 않습니다
    """
    item_channel = event['item']['channel']
    item_ts = event['item']['ts']
    reaction_user = event['user']

    reactions = app.client.reactions_get(
        channel=item_channel,
        timestamp=item_ts,
    )
    jira_gen_count = sum(
        d['count'] for d in reactions['message']['reactions']
        if d['name'] == emoji
    )
    if jira_gen_count > 1:
        say(
            channel=reaction_user,
            blocks=[
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f'이미 지라 이슈가 생성되었습니다.'
                    },
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f'이미 :{emoji}: 이모지가 스레드에 달려있어서 지라 이슈를 생성할 수 없습니다. 히스토리가 이미 지라 티켓으로 저장되었으니 어사인을 변경하시거나, 스레드에서 논의를 지속하거나, 이모지를 모두 지우고 다시 시도해보세요.'
                        },
                    ]
                }
            ],
        )
        return True
    return False


@contextlib.contextmanager
def loading_reaction(event):
    """
    GPT를 처리하는 동안 UX를 위해
    스레드에 loading 이모지를 추가합니다.
    """
    channel = event['item']['channel']
    item_ts = event['item']['ts']
    try:
        # Respond with an emoji directly to the thread
        app.client.reactions_add(
            channel=channel,
            name=SlackCollection.loading_emoji,
            timestamp=item_ts,
        )
    finally:
        ...

    try:
        yield
    finally:
        try:
            # Remove thumbsup reaction
            app.client.reactions_remove(
                channel=channel,
                name=SlackCollection.loading_emoji,
                timestamp=item_ts,
            )
        finally:
            ...


def laas_jira(event, say, collection: Union[PIThreadAll, PIThreadItem]):
    """
    GPT 호출에 시간이 걸리기 때문에 스레드에서 처리합니다.
    Lambda 에서 호출할 경우 FaaS를 사용하는 것이 좋습니다.
    https://slack.dev/bolt-python/concepts#lazy-listeners
    """
    # 성능을 위해 loading_reaction 의존성을 제거합니다.
    with loading_reaction(event):
        if check_emoji(event, say, collection.trigger_emoji):
            return

        slack = SlackOperator(event, say, collection.trigger_emoji)

        if not slack.get_conversation_data(root=collection.is_root):
            return


        gpt_response = slack.check_gpt_response(collection.laas_jira_hash, {'conversations': slack.context, 'schema': get_format_instructions(Issue)})
        gpt_metadata = slack.validate_gpt_response_json(gpt_response, say)

        reporter_email = slack.user_map.get(slack.item_user, {}).get('email') or outside_slack_jira_user_map(slack.item_user)
        assignee_email = slack.user_map.get(slack.reaction_user, {}).get('email') or outside_slack_jira_user_map(slack.reaction_user)

        issue = Issue.model_validate(gpt_metadata)

        jira = JiraOperator()
        jira.get_user_id_from_email(assignee_email)
        refined_fields = issue.refined_fields(
            jira.get_user_id_from_email(reporter_email),
            jira.get_user_id_from_email(assignee_email),
            slack.link,
        )

        try:
            jira_response = jira.safe_create_issues(refined_fields, slack.screenshots)
        except Exception as e:
            slack.say(
                channel=slack.reaction_user,
                blocks=[
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "Jira 이슈 생성에 실패했습니다."
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "plain_text",
                            "text": "이슈 타입별로 필수적인 필드가 있습니다. 필수 필드가 누락되지 않았는지 확인해보세요",
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "plain_text",
                            "text": "혹은 Jira 서버 오류로 인해 이슈 생성에 실패할 수 있습니다. 이런 경우 잠시 후 다시 시도해보세요.",
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"<{slack.link}|스레드 바로가기>"
                            }
                        ]
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"Error Message: ```{str(e)}```"
                            }
                        ]
                    },
                ]
            )
            raise e

        say(
            channel=slack.item_channel,
            blocks=issue.refined_blocks(jira_response, slack.item_user, slack.reaction_user, collection.workspace),
            # 스레드가 없으면 스레드를 생성합니다.
            thread_ts=slack.thread_ts or slack.item_ts,
        )



@app.event("reaction_added")
def reaction(event, say):
    """
    이모지에 따라 트리거되는 작업을 정의합니다.
    """
    match event['reaction']:
        case PIThreadAll.trigger_emoji:
            t = threading.Thread(target=laas_jira, args=(event, say, PIThreadAll), daemon=False)
            t.start()
        case PIThreadItem.trigger_emoji:
            t = threading.Thread(target=laas_jira, args=(event, say, PIThreadItem), daemon=False)
            t.start()


def os_term_handler(signum, frame):
    """
    이 함수는 운영 체제 시그널에 대한 핸들러입니다. 애플리케이션이 종료 시그널(SIGTERM)을 받으면 at_exit_handler() 함수를 호출합니다.

    AWS 콘솔에서 ECS 중지 버튼을 클릭한 경우는 SIGTERM 을 호출합니다.
    SIGTERM 이후 30초 동안 프로세스가 종료되지 않으면 SIGKILL 을 호출합니다.
    try - finally 로직을 타지 않습니다.
    """
    signame = signal.Signals(signum).name
    print(f'SIGNAL received: {signame} ({signum})')
    print('Frame:', frame)

    # 진행 중인 모든 non-daemon thread를 종료합니다.
    for thread in threading.enumerate():
        if thread is threading.main_thread() or thread.daemon:
            continue
        print(f'Terminating thread: {thread.name}, daemon: {thread.daemon}')
        thread.join()
    print('All non-daemon threads terminated')

    # main thread인 slack_handler 를 종료합니다.
    slack_handler.stop()


# Start your app
if __name__ == "__main__":
    signal.signal(signal.SIGINT, os_term_handler)
    signal.signal(signal.SIGTERM, os_term_handler)

    # Sentry 등 초기화 코드가 있다면 여기에 작성합니다.
    sentry_sdk.init(
        dsn=os.environ['SENTRY_DSN'],
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=1.0,
        # 세션 추적은 하지 않는다.
        auto_session_tracking=False,
    )
    slack_handler.start()
