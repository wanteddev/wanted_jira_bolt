import os
from io import BytesIO


class JiraOperator:
    def __init__(self):
        from atlassian import Jira
        self.base_url = 'https://wantedlab.atlassian.net'
        self.client = Jira(
            self.base_url,
            username=os.environ['ATLASSIAN_USER'],
            password=os.environ['ATLASSIAN_API_KEY'],
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
