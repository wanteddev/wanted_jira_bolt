FROM python:3.11-slim

LABEL maintainer="jongwon@wantedlab.com"

ENV HOME_DIR=/usr/local/wanted_jira_bolt

COPY . ${HOME_DIR}

WORKDIR ${HOME_DIR}

RUN pip install -r ${HOME_DIR}/requirements.txt

CMD ["python", "app.py"]