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
        description='이슈의 중요도를 나타내며 기본값은 "P3"입니다. 앱 설치불가, System Crash, 서비스 중단 등의 심각한 버그는 "P1"로 선택해주세요.'
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
    ]]] = Field(description='버그의 특성을 기술합니다. 유스 케이스의 누락, 비즈니스 로직 누락 등 요구사항이 불충분하여 발생한 버그는 "요구사항 미비"로 추가 선택해 주세요.'
                ' 기획에 명시된 내용/방향과 다르게 개발되어 발생한 버그는 "잘못된 구현(기획 의도와 다르게 구현)"으로 추가 선택해 주세요.'
                ' 개발 결과물이 요구사항을 충족하지 못하여 발생한 버그. 기획과 다르게 개발되어 발생한 버그는 "설정 및 환경 관련 이슈"로 추가 선택해 주세요.'
                ' API + 프론트/앱 간 오동작 등 모듈 또는 서비스의 통합 단계에서 발생한 버그는 "인티그레이션 이슈"로 추가 선택해 주세요.'
                ' 구문 오류, 예외처리 미비, 설정 오류 등으로 인한 버그는 "그 외 개발적 오류"로 추가 선택해 주세요.'
                ' 디자인 관련한 버그는 "디자인 QA 이슈"를 추가 선택해 주세요.'
                ' 신규 개발 아이템 작업으로 연관된 영역이 깨짐, 버그 수정으로 인해 기존 정상동작하던 영역이 깨짐 등 코드 수정이나 설정 변경 등의 변경사항에 의해 정상적으로 동작하던 영역이 오동작하여 발생한 버그는 "리그레션 이슈"로 추가 선택해 주세요.'
                ' 운영 장애 수준의 문제를 일으킨 버그의 경우에 "운영 장애"로 추가 선택해 주세요. 이 중 해당하는 부분을 모두 선택해주세요.')
    description: Optional[str] = Field(description='이슈의 상세 내용입니다. 버그가 발생한 상황, 버그의 영향도, 버그의 재현 방법 등을 기술해주세요.')
    due_date: Optional[date] = Field(description='이슈의 기한입니다. 이슈의 우선순위에 따라 기한을 설정해주세요.')

    def refined_fields(self, reporter_id, assignee_id, slack_link):
        self.description += f'\n\n*Slack Link*: {slack_link}\n_이 이슈는 Wanted Jira Bolt로부터 자동 생성되었습니다._'
        if self.issue_type == '버그':
            return {
                'project': {'key': 'PI'},
                'assignee': {'accountId': assignee_id},
                'reporter': {'accountId': reporter_id},
                'issuetype': {'name': self.issue_type},
                'description': self.description,
                'summary': self.summary,
                'duedate': str(self.due_date) if self.due_date else None,
                'priority': {'name': self.priority} if self.priority else None,
                'customfield_10106': {'value': self.environment} if self.environment else None,
                'customfield_10177': [{'value': prop} for prop in self.bug_property] if self.bug_property else None,
            }
        else:
            return {
                'project': {'key': 'PI'},
                'assignee': {'accountId': assignee_id},
                'reporter': {'accountId': reporter_id},
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
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f'*Priority*: {self.priority}',
                    },
                    {
                        "type": "mrkdwn",
                        "text": f'*Due Date*: {str(self.due_date) if self.due_date else None}',
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
