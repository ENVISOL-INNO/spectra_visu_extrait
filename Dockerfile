# syntax=docker/dockerfile:1

FROM python:3.12

WORKDIR /app

RUN apt-get update \
  && apt-get install -y \ 
  build-essential python3-dev \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* 

# Make pip < 24 so broken old packages don't fail
RUN pip install --upgrade "pip<24" setuptools wheel

# Pre-install numpy so old packages stop exploding
RUN pip install numpy==2.3.4


COPY requirements.txt .
COPY requirements-package.txt .

# Install the remaining requirements (no deps because already resolved)
RUN pip install -r requirements.txt --no-deps

RUN mkdir -p /home/vscode/.ssh && \
  ssh-keyscan github.com >> /home/vscode/.ssh/known_hosts

RUN --mount=type=ssh \
  GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=accept-new" \
  pip install -r requirements-package.txt

COPY . .

ENV PORT=10000

CMD ["sh", "-c", "uvicorn --factory main:create_app --host 0.0.0.0 --port ${PORT}"]

# Build command: 
# docker build --ssh default -t envisol/greensi:latest .