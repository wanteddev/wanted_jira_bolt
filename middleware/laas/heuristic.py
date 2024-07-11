def outside_slack_jira_user_map(slack_id):
    """
    일반적으로 조직 이메일로 매핑되지 않는 Slack 유저 ID를 Jira 유저 ID로 매핑한다.
    이메일이 매핑되지 않은 경우, 이슈 생성자가 지라에 등록된 사용자인지 확인해야 한다.
    """
    match slack_id:
        case 'U015NAVJQTF':                     # Sentry Bot
            return '5b08578531fcef2607e2a842'   # Sentry Jira User ID
        case _:
            return '557058:f58131cb-b67d-43c7-b30d-6b58d40bd077'    # Automation for Jira User ID
