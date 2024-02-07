import os
import json
import contextlib
from json import JSONDecodeError
from urllib.request import urlopen, Request, HTTPError
from threading import Thread

import sentry_sdk
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from middleware.laas import jira_summary_generator
from middleware.laas.heuristic import parse_environment, outside_slack_jira_user_map
from middleware.laas.jira_operator import JiraOperator


class SlackCollection:
    # FIXME:
    workspace = 'wantedx.slack.com'
    loading_emoji = 'loading'


class PICollection:
    # FIXME:
    workspace = 'wantedlab.atlassian.net'
    project = 'PI'
    trigger_emoji = 'pi_jira_gen'
    laas_jira_hash = 'b2cac55301e0fc435b14d49a2069731093e785dff7099dcd1677c0c794dfd177'


class SlackOperator:
    def __init__(self, event, client, say, trigger_emoji):
        self.event = event
        self.client = client
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

    def get_conversation_data(self):
        """
        스레드의 모든 메시지를 가져와 정제합니다
        """
        context = ''
        screenshots = []
        conversations = self.client.conversations_replies(
            channel=self.item_channel,
            ts=self.item_ts,
        )
        self.thread_ts = conversations["messages"][0].get("thread_ts")
        if self.thread_ts and self.thread_ts != self.item_ts:
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
            text = message.get("text", "")
            # Do something with the message text
            context += text + '\n'

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
    def slack_link(self):
        return f'https://{SlackCollection.workspace}/archives/{self.item_channel}/p{self.item_ts.replace(".", "")}{f"?thread_ts={self.thread_ts}" if self.thread_ts else ""}'

    def check_gpt_response(self, hash):
        """
        GPT 응답이 올바른지 확인합니다.
        이 단계는 LaaS 서버의 응답을 잘 받았는지 확인하는 단계입니다
        """
        try:
            gpt_response = jira_summary_generator(hash, self.context)
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
                                "text": f'<{self.slack_link}|스레드 바로가기>',
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
                                "text": f'<{self.slack_link}|스레드 바로가기>',
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
                                "text": f'<{self.slack_link}|스레드 바로가기>',
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
                                "text": f'<{self.slack_link}|스레드 바로가기>',
                            }
                        ]
                    }
                ],
            )
            raise e


def get_jira_account_id(slack, jira):
    # Get user info: Extract email from user info: permission 필요. users:read.email
    assignee_user_info = slack.client.users_info(user=slack.reaction_user)
    reporter_user_info = slack.client.users_info(user=slack.item_user)
    return {
        'assignee': jira.get_user_id_from_slack(assignee_user_info) or outside_slack_jira_user_map(slack.reaction_user),
        'reporter': jira.get_user_id_from_slack(reporter_user_info) or outside_slack_jira_user_map(slack.item_user),
    }


def safe_create_jira_issues(refined_fields, slack, jira):
    """
    Jira 이슈를 생성합니다.
    이 단계는 Jira API를 사용하여 이슈를 생성하는 단계입니다.
    """
    try:
        response = jira.client.create_issue(fields=refined_fields)
        if slack.screenshots:
            jira.update_attachments(issue_key=response['key'], attachments=slack.screenshots)
        return response
    except Exception as e:
        slack.say(
            channel=slack.reaction_user,
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
                            "text": f'지라 이슈를 생성하는 도중에 실패했습니다. 스레드 최상단에 이모지를 달면 스레드 내용을 분석해 스레드를 단 사람이 보고자, 이모지를 단 사람이 어사인되어 이슈를 생성합니다.',
                        },
                        {
                            "type": "mrkdwn",
                            "text": f'<{slack.slack_link}|스레드 바로가기>',
                        }
                    ]
                }
            ]
        )
        raise e


def screen_fields(metadata):
    """
    debug.issue_type_screen_metadata(project) 함수의 결과를 바탕으로 필드를 생성합니다.
    필드가 명시적으로 지정되어있는 이유는 Jira 화면 및 필드 구성을 프로젝트마다 다르게 할 수 있기 때문입니다.
    필수 필드는 Jira 화면 구성에서 필수로 지정되어있는 필드입니다 해당 필드를 지정하지 않으면 이슈 생성이 불가능합니다.
    화면 구성에 맞는 적절한 필드를 지정해주세요.
    """
    return {
        '버그': {
            'summary': metadata['summary'],
            'description': metadata['description'],
            'issuetype': {'name': metadata['issue_type']},
            'project': {'key': metadata['project']},
            'assignee': {'id': metadata['assignee']},
            'reporter': {'id': metadata['reporter']},
            # FIXME: example) PI 프로젝트의 버그 이슈 타입에는 이슈 화면 필드에 "발견된 환경" 필드가 필수입니다.
            'customfield_10106': {'value': metadata['environment']},
        },
        '작업': {
            'summary': metadata['summary'],
            'description': metadata['description'],
            'issuetype': {'name': metadata['issue_type']},
            'project': {'key': metadata['project']},
            'assignee': {'id': metadata['assignee']},
            'reporter': {'id': metadata['reporter']},
        },
    }


def check_emoji(event, client, say, emoji):
    """
    이미 스레드에 이모지, 즉 생성된 이슈가 있는지 확인합니다.
    스레드 내부에 이미 이모지가 있는 경우에는 이슈를 생성하지 않습니다
    """
    item_channel = event['item']['channel']
    item_ts = event['item']['ts']
    reaction_user = event['user']

    reactions = client.reactions_get(
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
def loading_reaction(event, client):
    """
    GPT를 처리하는 동안 UX를 위해
    스레드에 loading 이모지를 추가합니다.
    """
    channel = event['item']['channel']
    item_ts = event['item']['ts']
    try:
        # Respond with an emoji directly to the thread
        client.reactions_add(
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
            client.reactions_remove(
                channel=channel,
                name=SlackCollection.loading_emoji,
                timestamp=item_ts,
            )
        finally:
            ...


def laas_jira_thread(event, client, say, collection):
    """
    GPT 호출에 시간이 걸리기 때문에 스레드에서 처리합니다.
    Lambda 에서 호출할 경우 FaaS를 사용하는 것이 좋습니다.
    https://slack.dev/bolt-python/concepts#lazy-listeners
    """
    # 성능을 위해 loading_reaction 의존성을 제거합니다.
    with loading_reaction(event, client):
        if check_emoji(event, client, say, collection.trigger_emoji):
            return

        slack = SlackOperator(event, client, say, collection.trigger_emoji)
        if not slack.get_conversation_data():
            return

        jira = JiraOperator()

        gpt_response = slack.check_gpt_response(collection.laas_jira_hash)
        gpt_metadata = slack.validate_gpt_response_json(gpt_response, say)

        jira_account_id = get_jira_account_id(slack, jira)

        # Data Augmentation
        gpt_metadata['project'] = collection.project
        gpt_metadata['environment'] = parse_environment(gpt_metadata['environment'])
        gpt_metadata['description'] += f'\n\n*Slack Link*: {slack.slack_link}'
        gpt_metadata['description'] += f'\n_이 이슈는 Wanted Jira Bolt로부터 자동 생성되었습니다._'
        gpt_metadata['reporter'] = jira_account_id['reporter']
        gpt_metadata['assignee'] = jira_account_id['assignee']

        refined_fields = screen_fields(gpt_metadata)[gpt_metadata['issue_type']]
        jira_response = safe_create_jira_issues(refined_fields, slack, jira)
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f'Jira 이슈가 생성되었습니다!'
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f'<https://{collection.workspace}/browse/{jira_response["key"]}|{jira_response["key"]}>'
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f'*Summary*: {gpt_metadata["summary"]}',
                    },
                    {
                        "type": "mrkdwn",
                        "text": f'*Issue Type*: {gpt_metadata["issue_type"]}',
                    }
                ]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f'*Description*: {gpt_metadata["description"]}',
                    }
                ]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f'*Reporter*: <@{slack.item_user}>',
                    },
                    {
                        "type": "mrkdwn",
                        "text": f'*Assignee*: <@{slack.reaction_user}>',
                    }
                ]
            },
        ]
        if gpt_metadata['issue_type'] == '버그':
            # 버그 이슈인 경우 필수 필드인 환경 정보로 추가합니다.
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f'*Environment*: {gpt_metadata["environment"]}',
                        }
                    ]
                }
            )
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            # FIXME: 사내 가이드 문서가 필요한 경우 첨부합니다.
                            "text": f'<https://{collection.workspace}/wiki/spaces/QA/pages/82576189|버그 등록 가이드> 문서를 참고하여 이슈 필드를 수정해 주세요.',
                        }
                    ]
                }
            )

        say(
            channel=slack.item_channel,
            blocks=blocks,
            # 스레드가 없으면 스레드를 생성합니다.
            thread_ts=slack.thread_ts or slack.item_ts,
        )


# Initializes your app with your bot token and socket mode handler
app = App(token=os.environ['SLACK_BOT_TOKEN'])


@app.event("reaction_added")
def reaction(event, client, say):
    """
    이모지에 따라 트리거되는 작업을 정의합니다.
    """
    match event['reaction']:
        case PICollection.trigger_emoji:
            t = Thread(target=laas_jira_thread, args=(event, client, say, PICollection))
            t.start()


if __name__ == "__main__":
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
    SocketModeHandler(app, os.environ['SLACK_APP_TOKEN']).start()
