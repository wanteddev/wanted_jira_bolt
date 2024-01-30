import os
import requests


def call_wanted_api(method, path, **kwargs):
    """
    Wanted LaaS API를 호출합니다.
    """
    return requests.request(
        method=method,
        url=f"{LAAS_BASE_URL}{path}",
        headers={
            "project": LAAS_PROJECT,
            "apiKey": LAAS_API_KEY,
            "Content-Type": "application/json; charset=utf-8",
        },
        **kwargs,
    )


# FIXME 환경변수로 지정해주세요.
LAAS_BASE_URL = 'https://api-laas.wanted.co.kr'
LAAS_PROJECT = os.environ['LAAS_PROJECT']
LAAS_API_KEY = os.environ['LAAS_API_KEY']
