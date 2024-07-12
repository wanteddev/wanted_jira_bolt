"""
debug.issue_type_screen_metadata(project) 함수의 결과를 바탕으로 필드를 생성합니다.
필드가 명시적으로 지정되어있는 이유는 Jira 화면 및 필드 구성을 프로젝트마다 다르게 할 수 있기 때문입니다.
필수 필드는 Jira 화면 구성에서 필수로 지정되어있는 필드입니다 해당 필드를 지정하지 않으면 이슈 생성이 불가능합니다.
화면 구성에 맞는 적절한 필드를 지정해주세요.
"""
import json
from datetime import date
from typing import List, Optional, Literal

from pydantic import BaseModel, Field


def get_format_instructions(cls: BaseModel) -> str:
    """
    LangChain에서 사용하는 PydanticOutputParser.get_format_instructions 메서드를 대체합니다.
    """
    # Copy schema to avoid altering original Pydantic schema.
    schema = {k: v for k, v in cls.model_json_schema().items()}

    # Remove extraneous fields.
    reduced_schema = schema
    if "title" in reduced_schema:
        del reduced_schema["title"]
    if "type" in reduced_schema:
        del reduced_schema["type"]
    # Ensure json in context is well-formed with double quotes.
    return json.dumps(reduced_schema)


class Issue(BaseModel):
    """
    Wanted에서 발생한 이슈를 생성하기 위한 필드입니다.
    """
    summary: str = Field(description='이슈의 요약입니다.')
    issue_type: Literal['버그', '작업'] = Field(description='이슈의 타입입니다. 반드시 "버그" 또는 "작업" 중 하나를 선택해주세요.')
    # FIXME: example) PI 프로젝트의 버그 이슈 타입에는 이슈 화면 필드에 "발견된 환경" 필드가 필수입니다.
    environment: Literal['dev(개발 서버)', 'nextweek(테스트 서버)', 'wwwtest(스테이징 서버)'] = Field(
        description='이슈가 발견된 환경이며 기본값은 "dev(개발 서버)"입니다.'
         ' "dev(개발 서버)", "nextweek(테스트 서버)", "wwwtest(스테이징 서버)" 중 반드시 하나를 선택해주세요.'
         ' 운영 서버는 "wwwtest(스테이징 서버)"로 선택해주세요.'
    )
    priority: Literal['P1', 'P2', 'P3', 'P4'] = Field(
        description='이슈의 중요도입니다. 앱 설치불가, System Crash, 서비스 중단 등의 심각한 버그는 "P1"로 선택해주세요.'
          ' 빠른 수정이 필요한 기능 이상동작이나 UX 이슈는 "P2"로 선택해주세요.'
          ' 빠른 수정이 필요하지 않은 기능 이상동작이나 UX 이슈등을 포함하는 일반적인 버그는 "P3"로 선택해주세요.'
          ' "P4"는 일반적인 버그보다 우선순위가 낮은 버그입니다. 사용성에 지장을 주지않는 버튼이나 이미지의 모양/색깔/위치가 잘못된 이슈에 해당합니다.'
    )
    bug_property: Optional[List[Literal[
        '요구사항 미비',
        '잘못된 구현(기획 의도와 다르게 구현)',
        '설정 및 환경 관련 이슈',
        '인티그레이션 이슈',
        '그 외 개발적 오류',
        '디자인 QA 이슈',
        '리그레션 이슈',
        '운영 장애',
    ]]] = Field(description='버그의 특성을 기술합니다. "요구사항 미비", "잘못된 구현(기획 의도와 다르게 구현)", "설정 및 환경 관련 이슈", "인티그레이션 이슈", "그 외 개발적 오류", "디자인 QA 이슈", "리그레션 이슈", "운영 장애" 중 해당하는 부분을 모두 선택해주세요.')
    description: Optional[str] = Field(description='이슈의 상세 내용입니다. 버그가 발생한 상황, 버그의 영향도, 버그의 재현 방법 등을 기술해주세요.')
    due_date: Optional[date] = Field(description='이슈의 기한입니다. 이슈의 우선순위에 따라 기한을 설정해주세요.')

    def refined_fields(self, reporter_id, assignee_id, slack_link):
        self.description += f'\n\n*Slack Link*: {slack_link}\n_이 이슈는 Wanted Jira Bolt로부터 자동 생성되었습니다._'
        if self.issue_type == '버그':
            return {
                'project': {'key': 'PI'},
                'reporter': {'id': reporter_id},
                'assignee': {'id': assignee_id},
                'issuetype': {'name': self.issue_type},
                'description': self.description,
                'summary': self.summary,
                'duedate': str(self.due_date) if self.due_date else None,
                'customfield_10106': {'value': self.environment} if self.environment else None,
                'customfield_10177': [{'value': prop} for prop in self.bug_property] if self.bug_property else None,
            }
        else:
            return {
                'project': {'key': 'PI'},
                'reporter': {'id': reporter_id},
                'assignee': {'id': assignee_id},
                'issuetype': {'name': self.issue_type},
                'description': self.description,
                'summary': self.summary,
                'duedate': str(self.due_date) if self.due_date else None,
            }

    def refined_blocks(self, jira_response, item_user, reaction_user, workspace):
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
                    "text": f'이모지를 스레드 최상단에 달면 스레드 전체를 요약하고, 이모지를 내부에 달면 해당 메시지만 요약합니다. 생성된 내용을 확인해 주세요.'
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f'<https://{workspace}/browse/{jira_response["key"]}|{jira_response["key"]}>'
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        # repr 사용으로 개행문자를 이스케이프합니다.
                        "text": f'*Summary*: {repr(self.summary)[1:-1]}',
                    },
                    {
                        "type": "mrkdwn",
                        "text": f'*Issue Type*: {self.issue_type}',
                    }
                ]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f'*Description*: {self.description}',
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
        if self.issue_type == '버그':
            blocks += [
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f'*Environment*: {self.environment}',
                        },
                        {
                            "type": "mrkdwn",
                            "text": f'*Priority*: {self.priority}',
                        },
                    ]
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f'*Bug Property*: {", ".join(self.bug_property) if self.bug_property else None}',
                        }
                    ]
                },
                {
                    # FIXME: 사내 가이드 문서가 필요한 경우 첨부합니다.
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f'<https://{workspace}/wiki/spaces/QA/pages/82576189|버그 등록 가이드> 문서를 참고하여 이슈 필드를 수정해 주세요.',
                        }
                    ]
                },
            ]
        return blocks
