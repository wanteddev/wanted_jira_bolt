import os
import requests


def call_wanted_api(method, path, **kwargs):
    """
    Wanted LaaS API를 호출합니다.
    https://laas.wanted.co.kr/docs/guide/api/api-preset
    """
    return requests.request(
        method=method,
        url=f"https://api-laas.wanted.co.kr{path}",
        headers={
            "project": os.environ['LAAS_PROJECT'],
            "apiKey": os.environ['LAAS_API_KEY'],
            "Content-Type": "application/json; charset=utf-8",
        },
        **kwargs,
    )


def jira_summary_generator(hash, params: dict, messages: list):
    """
    Wanted LaaS API 중 Jira 생성기를 호출합니다.
    """
    return call_wanted_api('POST', '/api/preset/v2/chat/completions', json={
        "hash": hash,
        "params": params,
        "messages": messages,
    })
