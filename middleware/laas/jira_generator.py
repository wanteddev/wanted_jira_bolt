import os
from io import BytesIO

from middleware.laas import call_wanted_api


# FIXME 환경변수로 지정해주세요.
ATLASSIAN_USER = os.environ['ATLASSIAN_USER']
ATLASSIAN_API_KEY = os.environ['ATLASSIAN_API_KEY']
LAAS_JIRA_HASH = os.environ['LAAS_JIRA_HASH']


def summary_generator(context):
    """
    Wanted LaaS API 중 Jira 생성기를 호출합니다.
    """
    return call_wanted_api('POST', '/api/preset/chat/completions', json={
        "hash": LAAS_JIRA_HASH,
        "params": {"context": context},
    })


class JiraGenerator:
    def __init__(self):
        from atlassian import Jira
        self.base_url = 'https://wantedlab.atlassian.net'
        self.client = Jira(
            self.base_url,
            username=ATLASSIAN_USER,
            password=ATLASSIAN_API_KEY,
            cloud=True,
        )

    def update_attachments(self, issue_key, attachments):
        """
        Jira 이슈에 첨부파일을 업데이트합니다.
        """
        for attachment in attachments:
            self.client.add_attachment_object(issue_key, BytesIO(attachment))

    def get_user_id_from_slack(self, user_info):
        """
        Slack 유저 정보를 바탕으로 Jira 유저 ID를 가져옵니다.
        """
        try:
            email = user_info["user"]["profile"]["email"]
        except KeyError:
            return None
        resp = self.client.get(
            self.client.resource_url('user/search'),
            params={'query': email},
        )
        try:
            return resp[0]['accountId']
        except IndexError:
            return None
