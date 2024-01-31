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
from middleware.laas.jira_generator import JiraGenerator


class SlackCollection:
    # FIXME:
    workspace = 'wantedx.slack.com'
    trigger_emoji = 'pi_jira_gen'
    loading_emoji = 'loading'


class PICollection:
    # FIXME: anonymous 유저는 Wantedlab 에서 자동화에 사용하는 Automation for Jira 계정 ID 입니다
    workspace = 'wantedlab.atlassian.net'
    project = 'PI'


class WantedPIJira(JiraGenerator):
    def __init__(self, event):
        super().__init__()
        self.item_ts = event['item']['ts']
        # self.event_ts = event['event_ts']
        self.item_channel = event['item']['channel']
        self.item_user = event['item_user']
        self.reaction_user = event['user']

    def slack_link(self, ts):
        return f'https://{SlackCollection.workspace}/archives/{self.item_channel}/p{ts.replace(".", "")}'

    def check_jira_issue_exist(self, client, say):
        """
        이미 스레드에 이모지, 즉 생성된 이슈가 있는지 확인합니다.
        """
        reactions = client.reactions_get(
            channel=self.item_channel,
            timestamp=self.item_ts,
        )
        jira_gen_count = sum(
            d['count'] for d in reactions['message']['reactions']
            if d['name'] == SlackCollection.trigger_emoji
        )
        if jira_gen_count > 1:
            say(
                channel=self.reaction_user,
                blocks=[
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f'이미 지라 이슈가 생성되었습니다.'
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f'이미 :pi_jira_gen: 이모지가 스레드에 달려있어서 지라 이슈를 생성할 수 없습니다. 히스토리가 이미 지라 티켓으로 저장되었으니 어사인을 변경하시거나, 스레드에서 논의를 지속하거나, 이모지를 모두 지우고 다시 시도해보세요.'
                            },
                            {
                                "type": "mrkdwn",
                                "text": f'<{self.slack_link(self.item_ts)}|스레드 바로가기>',
                            }
                        ]
                    }
                ],
            )
            return True
        return False

    def check_gpt_jira_response(self, response, say, ts):
        """
        GPT 응답이 올바른지 확인합니다.
        이 단계는 LaaS 서버의 응답을 잘 받았는지 확인하는 단계입니다
        """
        try:
            gpt_response = response['choices'][0]['message']['content']
            return gpt_response
        except KeyError as e:
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
                                "text": f'너무 많은 글자수가 스레드에 있진 않은지 확인해 보세요.\nError Message: ```{response}```',
                            },
                            {
                                "type": "mrkdwn",
                                "text": f'<{self.slack_link(ts)}|스레드 바로가기>',
                            }
                        ]
                    }
                ],
            )
            raise e

    def validation_gpt_jira_response_json(self, gpt_response, say, ts):
        """
        GPT 응답이 올바른 JSON 형식인지 확인합니다.
        이 단계는 요구사항에 맞게 JSON 응답을 받았는지 확인하는 단계입니다
        """
        try:
            gpt_metadata = json.loads(gpt_response)
            return gpt_metadata
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
                                "text": f'<{self.slack_link(ts)}|스레드 바로가기>',
                            }
                        ]
                    }
                ],
            )
            raise e

    def safe_create_jira_issues(self, refined_fields, screenshots, say, ts):
        """
        Jira 이슈를 생성합니다.
        이 단계는 Jira API를 사용하여 이슈를 생성하는 단계입니다.
        """
        try:
            response = self.client.create_issue(fields=refined_fields)
            if screenshots:
                self.update_attachments(issue_key=response['key'], attachments=screenshots)
            return response
        except Exception as e:
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
                                "text": f'지라 이슈를 생성하는 도중에 실패했습니다. 스레드 최상단에 이모지를 달면 스레드 내용을 분석해 스레드를 단 사람이 보고자, 이모지를 단 사람이 어사인되어 이슈를 생성합니다.',
                            },
                            {
                                "type": "mrkdwn",
                                "text": f'<{self.slack_link(ts)}|스레드 바로가기>',
                            }
                        ]
                    }
                ]
            )
            raise e

    def get_jira_account_id(self, client):
        # Get user info: Extract email from user info: permission 필요. users:read.email
        assignee_user_info = client.users_info(user=self.reaction_user)
        reporter_user_info = client.users_info(user=self.item_user)
        return {
            'assignee': self.get_user_id_from_slack(assignee_user_info) or outside_slack_jira_user_map(self.reaction_user),
            'reporter': self.get_user_id_from_slack(reporter_user_info) or outside_slack_jira_user_map(self.item_user),
        }
    
    def get_conversation_data(self, client):
        """
        스레드의 모든 메시지를 가져와 정제합니다
        """
        context = ''
        screenshots = []
        conversations = client.conversations_replies(
            channel=self.item_channel,
            ts=self.item_ts
        )

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

        return {
            # 스레드의 최상단 메시지의 timestamp 를 따로 가져옵니다.
            'first_thread_ts': conversations["messages"][0]["ts"],
            'context': context,
            'screenshots': screenshots,
        }


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


@contextlib.contextmanager
def loading_reaction(client, channel, ts):
    """
    GPT를 처리하는 동안 UX를 위해
    스레드에 loading 이모지를 추가합니다.
    """
    try:
        # Respond with an emoji directly to the thread
        client.reactions_add(
            channel=channel,
            name=SlackCollection.loading_emoji,
            timestamp=ts,
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
                timestamp=ts,
            )
        finally:
            ...


def laas_jira_thread(event, client, say):
    """
    GPT 호출에 시간이 걸리기 때문에 스레드에서 처리합니다.
    Lambda 에서 호출할 경우 FaaS를 사용하는 것이 좋습니다.
    https://slack.dev/bolt-python/concepts#lazy-listeners
    """
    item_channel = event['item']['channel']
    item_ts = event['item']['ts']
    item_user = event['item_user']
    reaction_user = event['user']

    pi= WantedPIJira(event)
    with loading_reaction(client, item_channel, item_ts):
        if pi.check_jira_issue_exist(client, say):
            return

        jira_accounts = pi.get_jira_account_id(client)
        conversations = pi.get_conversation_data(client)

        # TODO: LaaS 의 서버 에러를 메시지로 보낼 필요도 있습니다. 현재 원티드는 외부 sentry로 확인합니다.
        response = jira_summary_generator(conversations['context']).json()

        gpt_response = pi.check_gpt_jira_response(response, say, conversations['first_thread_ts'])
        gpt_metadata = pi.validation_gpt_jira_response_json(gpt_response, say, conversations['first_thread_ts'])

        # Data Augmentation
        gpt_metadata['project'] = PICollection.project
        gpt_metadata['environment'] = parse_environment(gpt_metadata['environment'])
        gpt_metadata['description'] += f'\n\n*Slack Link*: {pi.slack_link(conversations["first_thread_ts"])}'
        gpt_metadata['description'] += f'\n_이 이슈는 Wanted Jira Bolt로부터 자동 생성되었습니다._'
        gpt_metadata['reporter'] = jira_accounts['reporter']
        gpt_metadata['assignee'] = jira_accounts['assignee']

        refined_fields = screen_fields(gpt_metadata)[gpt_metadata['issue_type']]
        jira_response = pi.safe_create_jira_issues(refined_fields, conversations['screenshots'], say, conversations['first_thread_ts'])
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
                    "text": f'<https://{PICollection.workspace}/browse/{jira_response["key"]}|{jira_response["key"]}>'
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
                        "text": f'*Reporter*: <@{item_user}>',
                    },
                    {
                        "type": "mrkdwn",
                        "text": f'*Assignee*: <@{reaction_user}>',
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
                            "text": f'<https://{PICollection.workspace}/wiki/spaces/QA/pages/82576189|버그 등록 가이드> 문서를 참고하여 이슈 필드를 수정해 주세요.',
                        }
                    ]
                }
            )

        say(
            channel=item_channel,
            blocks=blocks,
            thread_ts=item_ts,
        )


# Initializes your app with your bot token and socket mode handler
app = App(token=os.environ['SLACK_BOT_TOKEN'])


@app.event("reaction_added")
def reaction(event, client, say):
    """
    이모지에 따라 트리거되는 작업을 정의합니다.
    """
    match event['reaction']:
        case SlackCollection.trigger_emoji:
            t = Thread(target=laas_jira_thread, args=(event, client, say))
            t.start()


if __name__ == "__main__":
    # Sentry 등 초기화 코드가 있다면 여기에 작성합니다.
    sentry_sdk.init(
        dsn=os.environ['SENTRY_DSN'],
        environment='local',
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=1.0,
        # 세션 추적은 하지 않는다.
        auto_session_tracking=False,
    )
    SocketModeHandler(app, os.environ['SLACK_APP_TOKEN']).start()
