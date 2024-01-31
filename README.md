# Wanted Jira Bolt

## Too Long; Didn’t Read

<img width="372" alt="image" src="https://github.com/wanteddev/wanted_jira_bolt/assets/12846075/00666a25-1b88-4f71-8ef2-0f5a01b01b6b">

Wanted Jira Bolt 는 슬랙 스레드에 이모지를 달면 스레드 전체를 요약하여 Jira 티켓을 생성합니다!

사용방법은 단순합니다. 채널에 봇을 초대하고, 이모지를 달면 됩니다!

- 슬랙 봇을 채널에 초대하세요.
- 이모지를 스레드 최상단에 추가하세요.

초대하는 방법 중 간편한 방법으로 채팅창에 봇을 멘션하면 메시지 대신 <초대> 할 것이냐고 물어볼 겁니다!

## Abstract

### 이슈 관리는 업무 히스토리의 본질입니다.

이슈 관리는 소프트웨어 개발 프로세스를 효율적으로 관리하고 문제를 해결하여 품질을 향상시키며, 팀 협업을 강화하고 사용자 만족도를 높이는 데 큰 역할을 합니다.

많은 크고 작은 이슈들이 Jira 이슈로 생성되며 Jira 이슈 관리는 팀 간 소통과 협업을 촉진하기 위해, 이슈를 효과적으로 추적하고 해결하기 위해 많은 자동화 장치가 있습니다. 

하지만 아래와 같은 다양한 이유로 이슈를 생성하는 프로세스에 허들이 있습니다.

> Limitation 1. 형식적이지 않은 급한 보고는 슬랙으로 이루어집니다.

그리고 이런 급한 건은 이슈 만들 시간도 부족합니다.

> Limitation 2. 나중에 해야지 하는 백로그성 작업은 이슈 만들기를 놓칠 수도 있습니다.

“나중에 개선” 이라는 단어로 검색 한 번 해보세요.

메시지가 상당히 많다는 것에 공감하실거에요.

> Limitation 3. 이슈에 대한 논의가 슬랙 스레드, 지라 이슈 댓글로 갈라져 있어 추적이 쉽지 않습니다.

급한 변경 건에 대해서 지라 이슈 등록을 찾을 수 없는 경우도 있습니다.

> Limitation 4. 이슈를 요약 및 정리해서 다시 전달하는 프로세스가 깁니다.

스레드에서 논의한 내용을 요약해서 다시 이슈를 처음부터 작성해야 하고, 재현을 위해 스크린샷 등을 다시 찍어서 지라로 올리는 사례도 있습니다.

## Note

> Private 슬랙 채널에서는 이슈 생성이 되지 않습니다.

스레드에 있는 스크린샷을 공개로 복사하는걸 원하지 않는 사람도 있을 수 있고(권한이 없습니다),
지라 이슈에 슬랙 스레드 링크가 복사되는데, 특정 사람만 이슈추적이 가능한 Private 링크가 남는걸 원하지 않기 때문입니다.

> API 키가 있는 구성원에게 모든 알람이 가게 되니 주의하세요!

API 키가 있는 구성원이 이슈를 먼저 생성하고 자동으로 구성원을 할당하는 구조입니다.

## Prerequisite

현재 Production 운영 중인 슬랙 봇은

- Python 3.11 을 사용합니다.
- [Wanted LaaS](https://laas.wanted.co.kr/)를 사용합니다.
- Jira API 키가 필요합니다.
- Slack App 토큰과 Bot 토큰이 필요합니다.

## Wanted LaaS

### Prompt

#### System

```
You will be provided with a document delimited by triple quotes.
Your task is to extract document summaries and descriptions for Jira issue tickets.

Choose ONLY one from the list of Jira issue types provided here.
- 작업
- 버그

Choose ONLY one from the list of Environments in which the issue was discovered provided here.
- dev
- nw
- nextweek
- prod
- production
- wwwtest
- www

Ensure that summaries and descriptions contain all relevant context needed to interpret them - in other words don't extract small snippets that are missing important context. Provide output in JSON format as follows:

{"issue_type": "...", "environment": "...", "summary": "한글", "description": "한글"}

Provide summary and description value in Korean.
```

Jira 이슈 타입을 명시적으로 제공하셔야 합니다.(작업, 버그와 같이)

Wanted 는 environment 가 지라 이슈의 필수 필드에 해당하기 때문에 추가 휴리스틱이 들어가 있는데 이는 제거하셔도 좋습니다.
해당 코드를 참조하는 부분은 수정하셔야 합니다.

때로는 개발환경과 실환경의 용어를 De Facto로 구분하기도 하고, 사내에서만 사용하는 용어를 사용하기도 하기 때문에.
De Facto로 구분하는 경우는 GPT system prompt 를 사용하고, 사내에서만 사용하는 용어를 사용하는 경우를 De Facto 키 값을 참조하도록 하였습니다.

`middleware/laas/heuristic.py` 파일을 참고해 주세요.

#### User

```
Document: """${context}"""
```

### 필터 설정

- 모델: gpt-4
- 온도: 0
- 최대 길이(토큰): 4000
- 상위 P: 0
- 빈도 패널티: 0
- 존재 패널티: 0

## Jira API

아래 영역에서 API 토큰을 생성합니다.

> 프로필 > 계정 관리 > 보안 > API 토큰 만들기 및 관리

Jira는 매우 유연한 도구입니다.

이슈가 생성될 때는 화면 내의 필드에 필수 필드가 있는지, 어떤 커스텀 필드를 사용하는지 확인하시고 코드를 내부 문화에 맞게 수정하시는게 좋습니다.

워크플로우에 맞게 슬랙 메시지 UX를 변경하는 것이 좋습니다.

`debug.issue_type_screen_metadata` 함수를 참고하셔서 현재 필드에 어떤 데이터들이 화면에 그려지는지 확인하시는 것을 권장합니다.

```
ipython -i debug -- --project PI
```

## Slack 설정

https://api.slack.com/apps

아래 항목이 모두 체크되어 있어야 합니다.

- Event Subscriptions
    - Socket Mode 를 사용합니다.
- OAuth & Permissions
    - Bot Token Scopes
        - channels:history
        - channels:read
        - chat:write
        - chat:write.customize
        - chat:write.public
        - emoji:read
        - files:read
        - links:read
        - links:write
        - reactions:read
        - reactions:write
        - users:read
        - users:read.email
    - User Token Scopes
        - reactions:read

## Install

`.env` 파일에 환경변수를 구성합니다.

```
SLACK_APP_TOKEN=
SLACK_BOT_TOKEN=
ATLASSIAN_API_KEY=
LAAS_API_KEY=
LAAS_JIRA_HASH=
ATLASSIAN_USER=
LAAS_PROJECT=
SENTRY_DSN=
```

아래 명령어를 실행하여 로컬 테스트를 진행할 수 있습니다.

```
pip install -r requirements.txt
python app.py
```

.env 파일을 주입하여 Docker Standalone 방식으로 운영할 수 있습니다.
아래 명령어로 로컬 Docker 테스트도 진행 가능합니다.

```
docker build --no-cache -t wanted_jira_bolt .
docker run --rm -it --env-file=.env wanted_jira_bolt
```

## 안정적인 볼트 퍼포먼스를 위한 디테일한 장치들

지라 이슈를 이모지 만으로 생성한다고?! 라고 말씀하시면 오남용이 걱정되실 수도 있겠습니다.

아래와 같은 디테일을 추가했으니 볼트와 함께 삶의 질을 향상시켜보시죠!

> 스레드에서 처음 이야기한 사람이 “보고자” 가 되고 이모지를 단 사람이 “담당자” 가 됩니다.

일반적으로 보고자는 “빠르게 발견한 사람” 을 지정하고, 이모지를 단 사람은 "내가 이 작업을 하겠다!" 를 지정하는 것을 목적으로 만들어 졌습니다.

> 이모지를 남기면 직전까지 스레드에 있던 스크린샷은 자동으로 지라에 복사됩니다.

추가로 스레드 메시지가 동기화 되지는 않지만 슬랙 링크도 복사했으니 이슈 트래킹에는 문제가 없을거에요.

> 이슈 타입을 스레드에 명시해 주시면 좋습니다.

LaaS에 일부 휴리스틱이 있습니다. 명시적으로 스레드에 이거 "버그" 이슈입니다 라고 적고 이모지를 눌러보세요.

> "필수" 필드, 타 팀의 자동화에 유의하세요.

특히 QA팀의 자동화와 지라 이슈 생성에 충돌되는 부분이 있습니다. 템플릿이 있는 경우까지 고려하진 않았습니다.

볼트는 지라 이슈 생성을 보조하는 도구입니다. 올바른 버그 이슈 트래킹을 위해 QA의 가이드와 자동화에 유의하시고 부족한 필드는 직접 Jira 에서 수정하시는 것이 좋습니다.

> 보고자, 담당자가 봇이어도 동작합니다.

퇴사자나 담당자가 특정되지 않은 케이스일 경우 보고자 혹은 담당자로 배정할 수 있습니다.

`middleware.laas.heuristic.py` 에서 지정하실 수 있습니다.

---

## 문제가 발생했나요?

- 일반적인 몇몇 오류가 발생하면 왜 이슈 생성을 못했는지 이모지를 누른 유저에게 DM을 전송합니다.
- 스레드 내에 글자수가 너무 많다면 GPT 에 전달되지 않아서 에러가 납니다. DM 으로 대답할거에요.
- 이모지 특성상 중복 클릭이 쉽습니다. 중복 클릭할 경우 메시지를 DM 으로 보내도록 했습니다.
- 지라 티켓 생성 시 필수 필드가 생겼거나 Jira API 를 호출하는 데에 문제가 발생할 경우에는 봇을 만든사람이 수정해야 하는 문제일 확률이 높습니다.

원티드 내부 문화에 최적화된 봇이므로 수정이 필요합니다.

수정이 필요한 부분은 `FIXME` 를 검색해 주세요!

Issue raise, Pull Request 환영합니다!
