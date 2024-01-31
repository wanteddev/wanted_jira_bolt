def outside_slack_jira_user_map(slack_id):
    """
    일반적으로 조직 이메일로 매핑되지 않는 Slack 유저 ID를 Jira 유저 ID로 매핑한다.
    이메일이 매핑되지 않은 경우, 이슈 생성자가 지라에 등록된 사용자인지 확인해야 한다.
    """
    match slack_id:
        case 'U015NAVJQTF':
            return '5b08578531fcef2607e2a842'
        case _:
            return '557058:f58131cb-b67d-43c7-b30d-6b58d40bd077'


def parse_environment(environment):
    """
    GPT의 휴리스틱을 적용하기 위한 함수
    때로는 개발환경과 실환경의 용어를 De Facto로 구분하기도 하고, 사내에서만 사용하는 용어를 사용하기도 한다.
    De Facto로 구분하는 경우는 GPT system prompt 를 사용하고, 사내에서만 사용하는 용어를 사용하는 경우를 De Facto 키 값을 참조하도록 한다.

    원티드에서는 이슈타입을 작업, 버그로만 구별하기 때문에 이슈타입에는 휴리스틱을 적용하지 않는다.

    원티드에서는 "발견된 환경" 이름이 특수한 경우가 많다.
    - dev(개발 서버)
    - nextweek(테스트 서버)
    - wwwtest(스테이징 서버)
    """
    environment = environment.lower()
    if 'dev' in environment:
        return 'dev(개발 서버)'
    elif ('nw' in environment) or ('nextweek' in environment):
        return 'nextweek(테스트 서버)'
    elif 'www' in environment:
        return 'wwwtest(스테이징 서버)'
    else:
        return 'dev(개발 서버)'