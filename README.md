

# Honey LLM / LLMPot 

## Overview

This repository provides code for an Ollama honeypot, though it currently only supports Ollama's own endpoints and the `/v1/models` endpoint as the focus of the honeypot is more on Ollama than on other LLM interfaces/frameworks.

***Important:*** This overview is not meant to be exhaustive, it is merely here to explain some of the basics needed to use the honeypot. If you want more info, explore the code yourself for more details. There should be plenty of comments to thoroughly explain various design choices (and perhaps confuse you; sorry in advance).

The honeypot includes two different interaction levels, each stored in their own branches:
* `main`
* `LIH`

The `LIH` branch is for a low-interaction-version of the honeypot, which focuses mostly on correct/realistic error messages and response structures, though it still attempts to create mostly realistic response values as well - to a degree. Its responses to acceptable prompt requests are all the same, static greeting message. Importantly, the LIH does not attempt to change its own internal state, beyond storing the IP and headers of incoming requests when they are initially received. 

The `main` branch is for a medium-interaction-version of the honeypot (the "MIH"), which acts as an extension of the LIH. Instead of returning only static responses to valid/acceptable prompts, a certain degree of prompt analysis is performed. Files containing this code can be found in `./response_cache/generate_cache` and `./response_cache/chat_cache` for the code for `/api/generate` and `/api/chat`, respectively.

The gist of the prompt analysis is that a cache of a few specific prompt responses are stored, and the MIH also attempts to guess as to whether prompts are requesting specific responses, e.g., the result of a simple mathematical expression, or a particular phrase/word. A few cache entries exist to handle prompts such as "what model are you?" and "please introduce yourself" but this is not an exhaustive list of prompt types.

The prompt analysis itself is also inherently flawed, given its use of a small dictionary of words to remove from prompts when attempting to extract what is believed to be the response the prompt is asking for. This can lead to responses from the honeypot still containing some words from the original prompt which the honeypot failed to identify and remove. Likewise, returning mathematical calculation results usually takes priority, and the honeypot currently assumes that prompts containing math (and math-looking expressions such as value ranges, e.g., "list the numbers 1-5") always want the calculation result returned as the sole response.

There are plenty of other limitations, but these may be some of the most relevant - at least from memory.


## Local Deployment Setup
This honeypot system was developed in a Python virtual environment (`venv`) running Python `3.12.10`.

To host the honeypot locally, setting up a new Python virtual environment is recommended.

Assuming a fresh Python environment, run the following commands to prepare the environment to host the honeypot:

```
python -m pip install --upgrade pip
```

```
pip install fastapi[standard]
```

It is also possible to simply install the `requirements.txt` file included in this Github Repository - this will include other, non-essential dependencies as well such as Discord-related packages used to run the Discord bot (bot code stored in `./discord_bot`)

The easiest way to do this is to navigate to the repository folder on the hosting machine and executing the following command:

```
pip install -r .\requirements.txt
```


## Logging

When deployed locally, and unless a custom environment variable, `LOG_DIR`, is set, the honeypot will log to the folder `./logs`.

Further, logs will all be stored in the file "`in-out.log`" unless a custom filename is given via the `LOG_FILE` environment variable.

Neither the `LOG_DIR`, nor `LOG_FILE` environment variables exist by default, so the user must simply create these on their own in the existing `/.env` file if they want to change the logging directory and/or the filename of the produced log file.

By default, the logging does **NOT** log the headers of incoming requests, but this can be toggled on by setting the value of the `LOG_HEADERS`-environment variable to `true` - or some similar truth-like value; see the `log_and_return` method in `./loggging_resources.py` for the specifics.


### Logged values

The values that are logged are the following (determined by the custom `LogEntry` class found in `./classes/loggging_classes.py`, and used in the `JSONFormatter` class in `./loggging_resources.py`):

```
* time: str
* source_ip: str | None = None
* http_method: str
* endpoint: str
* status_code: int
* streamed: bool | None = None
* headers: dict[str, str] | None = None
* request_hex_dump: str | None = None
* error_data: dict[str, Any] | None = None
* request_body: dict[str, Any] | BaseRequest | None = None
* response: dict[str, Any] | BaseResponse | None = None
```


## Docker deployment

A Dockerfile is included to allow for the honeypot to be deployed on, e.g., a Linux VM, rather than running the honeypot locally.

To go along with this, a shell script (`build_Host.sh`) has been created to be run on the host machine, in order to create an image for the honeypot. **Note:** This script is mainly intended to be used on a Windows machine and has *not* been tested in a Linux environment. The script, itself, is simple, and is mainly for the convenience of the developer. If it doesn't work for you, simply create your own script or just run the individual commands manually if you want.


### Setup used for the Docker image

The honeypot container itself uses its own, non-root user, and it expects this user to exist already in the environment it is deployed to. This environment is assumed to be a Linux environment and deployment of the honeypot container has not been thoroughly tested for a Windows VM.

Specifically, for the setup of a Linux VM, a user with a User ID (`UID`) and Group ID (`GID`) of `20001` is assumed to exist, as is it assumed that the logging folder exists already and that this custom user has access to it.

A list of various commands used by the developer during implementation and deployment - including some used for the Linux environment setup such as the `acl` commands - can be found in `./various linux commands I used.txt`.

This list is **not** guaranteed to be complete, as certain commands may have been overlooked or forgotten, but it is the developer's belief that they *should* provide - or at least mostly provide - the user with a functioning system.

Certain necessities are also **not** described in this list of commands, including commands to create the folders for logging - the commands at the end of this list assume these folders (and honeypot logging file!) to exist.

Upon building the honeypot image with `build_Host.sh`, the honeypot can be run using the command (as was used for deployment by the developer):

```
docker run -d --restart unless-stopped \
--name {HP_CONTAINER} \
--network host \
--mount type=bind,src=/{FULL_BASE_LOG_PATH}/honeypot-logs,dst={CONTAINER_LOG_PATH}/ \
-e LOG_DIR={CONTAINER_LOG_PATH}/ 
```

where:
* `HP_CONTAINER` is the desired name of the honeypot container, e.g., `HP_CONTAINER` = `honey-llm`
* `FULL_BASE_LOG_PATH` is the desired path to the folder where the honeypot should create its own logging folder (hard-coded in the `run` command as `/honeypot-logs`), e.g., `FULL_BASE_LOG_PATH` = `/home/ubuntu/honey-llm-logs`.
* `CONTAINER_LOG_PATH` is the internal container path where logs will be accessible for the container itself, e.g., `CONTAINER_LOG_PATH` = `/apps/logs`

**NOTE** especially the src mount directory which the honeypot container must have access to, including the logging file!

While a configuration with the aforementioned VM user, prepared directories, and permissions, the developer cannot guarantee that some details have been overlooked. Though this should provide/create a functioning honeypot deployment, with correct request handling and subsequent logging, it has not sufficiently tested from scratch to guarantee that this is all that is needed, nor if more steps are taken than really necessary for this honeypot deployment.

The reader/user is thus advised to test this out on their own as well, to figure out what might work and what might (potentially) not, should they wish to deploy this honeypot themselves.



## Discord Bot

This bot is used to simplify the maintenance of the deployed honeypots, and has served as the primary means of starting/stopping both the honeypots and the `tcpdump` containers running alongside the honeypots.

A variety of environment variables are used for this bot (see `./discord_bot/.env`), primarily different values pertaining to each of the honeypot hosts (e.g., host IPs, container names, etc.).

***Important:*** Not included in the bot's `.env` file are a number of more sensitive details, e.g., the bot's token. This file is simply called `.env.secret`. Values obtained from this file are noted using comments in the code (see `./discord_bot/health_checker.py`).

Should the user wish to run this bot themselves, they will need to create these variables on their own and include them in such a file - or, alternatively, hard-code these values into the bot code itself (caution is, of course, advised if this is done!).

The developed Discord bot provides a variety of commands:
* `!psall`: Run `docker ps -a` on the host the bot has connected to.
* `!honey`: Check the status of the honeypot and, if it's not running, restart it.
* `!tcp`: Check the status of the `tcpdump` container and, if it's not running, restart it.
* `!honey_latest`: Check the 5 latest logs from the honeypot (**Note:** this tends to fail if the last 5 logs are too long to send in a Discord message!)
* `!tcp_latest`: Check the 5 latest logs from the latest `.pcap` file (**Note:** this is formatted to provide just timestamps, involved IPs, and involved ports, thus it never fails)
* `!honey_purge`: Stop and remove the honeypot container.
* `!tcp_purge`: Stop and remove the `tcpdump` container.
* `!fetch`: Stop the containers, fetches the logs from them and deletes these on the host if fetching succeeded, then restarts containers previously running.





















