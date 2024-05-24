from argparse import ArgumentParser

from middleware.laas.jira_operator import JiraOperator


class DebugJiraGenerator(JiraOperator):
    def get_jira_screens(self):
        resp = self.client.get(
            self.client.resource_url('screens'),
            params={'maxResults': 100, 'startAt': 0, 'expand': 'screenScheme'},
        )
        screens: list = resp['values']
        while resp['isLast'] is False:
            resp = self.client.get(
                resp['nextPage'].removeprefix(self.base_url),
                params={'expand': 'screenScheme'},
            )
            screens.extend(resp['values'])
        return screens

    def get_jira_screen_schemes(self):
        start = 0
        resp = self.client.get(
            self.client.resource_url('issuetypescreenscheme') + '/mapping',
            params={'maxResults': 100, 'startAt': start},
        )
        screen_schemes: list = resp['values']
        while resp['isLast'] is False:
            start += 100
            resp = self.client.get(
                self.client.resource_url('issuetypescreenscheme') + '/mapping',
                params={'maxResults': 100, 'startAt': start},
            )
            screen_schemes.extend(resp['values'])
        return screen_schemes


def issue_type_screen_metadata(project):
    """
    https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-type-screen-schemes/#api-group-issue-type-screen-schemes

    이 API를 통해 프로젝트의 스크린 구성을 가져올 수 있습니다.
    """
    jg = DebugJiraGenerator()

    screens = jg.get_jira_screens()
    screen_schemes = jg.get_jira_screen_schemes()
    issue_type_map = {d['id']: d['name'] for d in jg.client.get_issue_types()}

    datarq_screens = [s for s in screens if s['name'].startswith(f'{project}:')]
    datarq_screen_schemes = [
        dict(x, **{'screen_id': d['id'], 'screen_name': d['name'], 'screen_description': d['description']})
        for d in datarq_screens if d.get('screenSchemes')
        for x in d['screenSchemes']['values']
    ]
    for s in datarq_screen_schemes:
        s['issue_type_id'] = [x['issueTypeId'] for x in screen_schemes if str(x['screenSchemeId']) == str(s['id'])]
        s['screen_fields'] = jg.client.get_all_screen_fields(s['screen_id'])

    return {
        issue_type_map.get(x, x): d
        for d in datarq_screen_schemes
        for x in d['issue_type_id']
    }


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--project', required=True)
    args = parser.parse_args()

    metadata = issue_type_screen_metadata(args.project)
    print(metadata)