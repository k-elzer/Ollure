from ast import parse as ast_parse, Expression, Constant, BinOp, UnaryOp, Add, Sub, Mult, UAdd, USub
from re import compile as re_compile


# tiny helper function to avoid repeating code:
def words_to_nums():
    return {
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
    }

# helper method to determine amount of times a prompt might need to be repeated in the response,
# depending on what the client wanted (e.g., "say hi in 3 words", "reply with hello five times", etc.)
# SUGGESTED BY COPILOT
def _extract_requested_reply_repeat_count(prompt: str) -> int:
    lowercase_prompt = prompt.lower()

    # pattern to match numbers - both as digits and as written words (e.g., "three")
    count_pattern = r"(?:\d{1,2}" + r'|' + r'|'.join(words_to_nums().keys()) + r")"

    # small helper method to parse the requested repetition count
    def parse_repeat_count(count_text: str) -> int:
        if count_text.isdigit():
            return int(count_text)

        return words_to_nums().get(count_text, 1)

    # regex patterns to find different ways that repitition may have been requested:
    # (patterns inclue a group named "count" to extract the relevant part of the prompt,
    # and uses the "count_pattern" to also match numbers written in words, e.g., "three")
    for pattern in (
        r'\b(?:say|repeat|write|reply|respond)\b[\s\S]{0,40}?\b(?P<count>' + count_pattern + r')\s+(?:times?|words?)\b',
        r'\bin\s+(?P<count>' + count_pattern + r')\s+words?\b',
        r'\b(?P<count>' + count_pattern + r')\s+times?\b',
    ):
        repeat_count_match = re_compile(pattern).search(lowercase_prompt)

        if repeat_count_match != None:
            repeat_count = parse_repeat_count(repeat_count_match.group("count"))

            if repeat_count > 1:
                return repeat_count

    # if above patterns didn't match, check also for the words "twice" and "thrice", just in case
    # (this is mainly just to be sure that such requests are also caught, despite not being very likely to be the case)
    if re_compile(r'\btwice\b').search(lowercase_prompt) != None:
        return 2

    if re_compile(r'\bthrice\b').search(lowercase_prompt) != None:
        return 3

    return 1

# helper method to repeat a requested reply for however many times the client might want
def _repeat_requested_reply(requested_reply: str, prompt: str) -> str:
    repeat_count = _extract_requested_reply_repeat_count(prompt)

    if repeat_count <= 1 or requested_reply == "":
        return requested_reply

    # if the repetition count is part of the extracted requested reply;
    # assume this to be *unintentional* and remove it before repeating the reply
    if str(repeat_count) not in requested_reply:
        # if count was a number, get the corresponding word for it, and remove this word from the requested reply
        num_as_word = list(words_to_nums().keys())[list(words_to_nums().values()).index(repeat_count)]
        requested_reply = requested_reply.replace(num_as_word, "", 1).strip()

    else:
        requested_reply = requested_reply.replace(str(repeat_count), "", 1).strip()

    return ' '.join([requested_reply] * repeat_count)


# helper method to extract a mathematical expression the client might want calculated
# SUGGESTED BY COPILOT
def _extract_calculation_expression(prompt: str) -> str:
    lowercase_prompt = prompt.lower()

    # patterns to help determine if the client wants something calculated.
    # First pattern tries to look for indicator words like "what is", "how much is", "calculate", etc.
    # Second pattern tries to find the expression itself.
    request_patterns = (
        r'\b(?:what\s+is|how\s+much\s+is|calculate(?:\s+the\s+product)?|compute|find)\b',
        r'^\s*[\d(][\d\s\+\-\*\(\)=\?\.]*[\+\-\*][\d\s\+\-\*\(\)=\?\.]*$',
    )
    if not any(re_compile(pattern).search(lowercase_prompt) != None for pattern in request_patterns):
        return ""

    # only look at characters relevant for the calculation, allowing only digits, some operators, parentheses, and spaces
    # (division is intentionally left out, mainly to avoid extra edge-case handling and since it's not as likely to be requested)
    # TODO: ADD SUPPORT FOR DIVISION!
    for candidate_match in re_compile(r'[\d\+\-\*\(\)\s]+').finditer(lowercase_prompt):
        candidate_expression = re_compile(r'\s+').sub('', candidate_match.group(0))

        if candidate_expression == "":
            continue

        # verify that the expression makes sense to try to evaluate
        if re_compile(r'\d').search(candidate_expression) != None and re_compile(r'[\+\-\*]').search(candidate_expression) != None:
            return candidate_expression

    return ""


# helper method to evaluate an extracted expression the client might want calculated
# SUGGESTED BY COPILOT
def _evaluate_calculation_expression(expression: str) -> str:
    def evaluate(node):
        if isinstance(node, Expression):
            return evaluate(node.body)

        if isinstance(node, Constant) and isinstance(node.value, (int, float)):
            return node.value

        if isinstance(node, BinOp):
            left_value = evaluate(node.left)
            right_value = evaluate(node.right)

            if isinstance(node.op, Add):
                return left_value + right_value

            if isinstance(node.op, Sub):
                return left_value - right_value

            if isinstance(node.op, Mult):
                return left_value * right_value

            return left_value

        if isinstance(node, UnaryOp):
            operand_value = evaluate(node.operand)

            if isinstance(node.op, UAdd):
                return +operand_value

            if isinstance(node.op, USub):
                return -operand_value

        return left_value

    parsed_expression = ast_parse(expression, mode="eval")
    result = evaluate(parsed_expression)

    if isinstance(result, float) and result.is_integer():
        result = int(result)

    return str(result)


def lookup(model: str, prompts: list[str]):
    inputs = [] # list to store incoming contents of the prompts
    responses = [] # list to store the pre-generated responses appropriate for the response to the request

    # loop through every prompt in the list of messages:
    # for each prompt, check all the things it prompts for, and add each one that hasn't already been answered/handled
    for prompt in prompts:
        if prompt == None:
            inputs.append(prompt) if None not in inputs else None # "None" and "" are both valid, but give different responses

        # "None" causes issues for the "in" operator, so only continue checks if the prompt wasn't "None"
        else:
            lowercase_prompt = prompt.lower() # avoid case sensitivity issues
            reply_indicators = ["say", "only", "just", "exactly", "simply", "one", "short", "nothing", "reply", "with", "write", "repeat", "respond"] # ? words that might indicate that the client wants a specific reply

            if prompt == "":
                inputs.append(prompt) if "" not in inputs else None

            # only include the standard "hi" greeting response if the client didn't request a short or one-word response (e.g., "just say hi" or "reply only with: Hello")
            if (any(greeting in lowercase_prompt for greeting in ["hi", "hello", "hey"])
                and not any(greeting in lowercase_prompt for greeting in reply_indicators)):
                inputs.append("hi") if "hi" not in inputs else None
            
            # if a prompt is asking something like "are you there":
            if "you there" in lowercase_prompt:
                inputs.append("here") if "here" not in inputs else None

            # this check will match requests like "introduce yourself", "tell me something about you", "tell me a bit about you", "describe yourself", "explain your model", etc.
            if (any(word in lowercase_prompt for word in ["you", "model"])
                and any(word in lowercase_prompt for word in ("intro", "something", "about", "describe", "explain"))):
                # if the model has already introduced itself, don't start the introduction reply with another "Hello!":
                if "hi" not in inputs:
                    responses.append("Hello!")
                # append an appropriate introduction based on the model being prompted
                # (defaulting to a generic introduction in case the prompted model doesn't have a cached introduction)
                model_intro = "introduction_generic"
                if "llama" in model:
                    model_intro = "introduction_llama"
                elif "gemma" in model:
                    model_intro = "introduction_gemma"
                elif "qwen" in model:
                    model_intro = "introduction_qwen"
                inputs.append(model_intro) if model_intro not in inputs else None

            if "united states" in lowercase_prompt:
                inputs.append("united states") if "united states" not in inputs else None

            if "today" in lowercase_prompt and any(word in lowercase_prompt for word in ("day", "date")): # checks the prompt for: "today" AND ("day" OR "date")
                inputs.append("today") if "today" not in inputs else None

            if "strawberry" in lowercase_prompt: # assuming strawberries are only brought up if the client wants 'r's in "strawberry" counted
                inputs.append("strawberry") if "strawberry" not in inputs else None

            if "ping" in lowercase_prompt:
                inputs.append("ping") if "ping" not in inputs else None

            if all(word in lowercase_prompt for word in ("sky", "blue")):
                inputs.append("sky blue") if "sky blue" not in inputs else None
            
            if re_compile(r'[\u4E00-\u9FFF]').findall(lowercase_prompt) != []: # if there were chinese characters in the prompt:
                # TODO: MAKE THIS MORE DYNAMIC SOMEHOW
                inputs.append("chinese") if "chinese" not in inputs else None # any chinese characters present will result in the same response (a summary of the movie "Farewell My Concubine" in Chinese)

            # check for quotes in the prompt, in case the user wants a very specific phrase for the response.
            # The regex here looks for the space-separated words written in the re_compile() method call, for at most 80 characters,
            # then marks this requested reply (in a case-*INSENSITIVE* manner) as a group named "reply" if it's enclosed in either single or double quotes,
            # and extracts it for the response if it was found
            quoted_reply_match = re_compile(r'(?:' + '|'.join(reply_indicators) + r')[\s\S]{0,80}?["\'](?P<reply>[^"\']+)["\']', 2).search(prompt) # ? the '2' is what makes this regex case-insensitive

            # check if the prompt is asking for a specific reply using a colon instead of a quoted phrase
            # the regex here first checks for a word, then for potential whitespace, then a colon, then for any additional whitespace, and then captures whatever comes after the colon
            # (e.g., "reply with exactly this text and nothing else: ok")
            # ? this regex assumes the requested reply is the last thing in the prompt, which seems to also be the case in the logs gathered so far
            exemplefied_reply_match = re_compile(r'\w\s*:\s*(?P<reply>.+)', 2).search(prompt) # ? the '2' is what makes this regex case-insensitive

            # if a prompt requests the exact model name of a model, simply return this as the sole response,
            # HOWEVER, only do so if the prompt isn't explicitly trying to request a specific reply from the system
            # (i.e., the above quotation and colon regexes didn't match)
            if ([quoted_reply_match, exemplefied_reply_match] == [None, None]
                and "model" in lowercase_prompt and any(word in lowercase_prompt for word in ("exact", "name", "you"))):
                return model[:model.find(':')] if ':' in model else model

            # check if the prompt wants a calculation done, and if so, try to extract and evaluate it
            # ? if a calculation is to be done (and succeeds), this result will be all that is returned from the lookup!
            calculation_expression = _extract_calculation_expression(prompt)
            if calculation_expression != "":
                try:
                    return _evaluate_calculation_expression(calculation_expression)
                except (SyntaxError, ValueError, TypeError, ZeroDivisionError):
                    pass

            # use regex to check for requests like "only reply with ok", "JustSayHello", "simply reply with 'hello there'", etc.,
            # and only respond with this requested reply
            # (allowing just the word "short" to trigger this regex matching and response isn't necessarily the best, e.g., if users ask for a short summary, or review, etc.)
            # THIS ENTIRE IF-STATEMENT WAS PRACTICALLY ALL WRITTEN BY COPILOT! Copilot wrote all the regex used, with the original code being the part that runs if all the regex matching fails
            if any(greeting in lowercase_prompt for greeting in reply_indicators):
                # split prompt up into separate words, in case the request was in camel case (e.g., "JustSayHello")
                spaced_prompt = re_compile(r'(?<=[a-z])(?=[A-Z])').sub(' ', prompt)

                # variable to store the requested reply after it has been determined/extracted
                requested_reply = ""

                # if the client explicitly quoted a specific reply, simply respond with whatever this quoted reply was (response won't include the quotes)
                # ! don't check if any extracted reply is in the input or not,
                # ! as this will cause issues in case the reply happens to be the same as the key used in the response cache!
                if quoted_reply_match != None:
                    requested_reply = quoted_reply_match.group("reply")

                # if a requested reply wasn't explicitly quoted, check if a colon was used instead (e.g., "Reply with exactly this text and nothing else: ok")
                elif exemplefied_reply_match != None:
                    requested_reply = exemplefied_reply_match.group("reply")

                # if requested reply wasn't quoted nor described using a colon, try to guestimate what the client intended for the reply to be:
                else:
                    # define a list of words to filter out of the prompt, and remove them from the spaced version of the prompt (this also turns "JustSayHello" into "Hello"),
                    # then remove any remaining special characters,
                    # and combine adjacent spaces into one, and trim away leading and trailing spaces.
                    # This should (hopefully) leave the requested reply as the only words left in the prompt
                    regex_word_filter = r"\b(?:please|just|with|only|exact|exactly|simply|say|one|word|words|write|text|repeat|reply|respond|time|times|no|nothing|else|other|explain|explanation|answer|short|the|a|an|do|not|that|that's|don't|any|thing|anything|to|for|me|I|in|and)\b"
                    extracted_reply = re_compile(regex_word_filter, 2).sub(' ', spaced_prompt)
                    extracted_reply = re_compile(r'[\t\r\n:;,.!?_\-]+').sub(' ', extracted_reply)
                    extracted_reply = re_compile(r'\s+').sub(' ', extracted_reply).strip()

                    if extracted_reply != "":
                        # return the extracted reply if this extraction succeeded
                        requested_reply = extracted_reply
                    else:
                        # if extraction failed for whatever reason, simply check the request for some specific common replies
                        for requested_reply in ["hi", "hello", "hey", "ok", "yes", "no", "sure"]:
                            if requested_reply in lowercase_prompt:
                                # search the prompt for each of the possible, common requested replies in a case-*INSENSITIVE* manner
                                requested_reply_match = re_compile(requested_reply, 2).search(prompt)

                                if requested_reply_match != None:
                                    # return the requested reply if it was found
                                    # ? (this reply will retain the same capitalization as it was in the prompt, due to the case-insensitive regex search)
                                    requested_reply = requested_reply_match.group(0)
                                else:
                                    # if (somehow) none of the above methods worked, simply return the same, lowercase reply that was found in the prompt
                                    # ? (this will naturally NOT retain the same capitalization as it was in the prompt)
                                    requested_reply = requested_reply

                                # break after the first match, since the client is assumed to have wanted only whatever they requested first
                                # (or they would've quoted it to specify otherwise)
                                break

                # if a requested reply was found, assume the client only wanted this reply - repeat it if this was (seemingly) requested!
                # ? this also cuts off any later chat messages;
                # ? if the client's first chat message is "only say hi", then this will be all that is responded with
                if requested_reply not in ("", None):
                    return _repeat_requested_reply(requested_reply, prompt)

            if inputs == []:
                inputs.append("default")

    for input in inputs:
        responses.append(_response_cache.get(input)) # no default value needed for the ".get()", as "None" is part of the dictionary

    return ' '.join(responses) # join all responses together into a single string before returning!


# DICTIONARY CONTAINING PRE-GENERATED RESPONSES (values) FOR DIFFERENT PROMPTS (keys)
# (both "None" and "" are valid request prompts, so both are included in this dictionary too)
_response_cache = {
    None:
        "It seems the question is missing. Can you please provide more details? I'm here to help with any questions or tasks you may have.",
    "":
        "It seems like you were about to ask a question, but it got cut off. What's on your mind? I'm here to help with anything you'd like to discuss or explore!",
    "default":
        "Sorry, but I've been instructed not to answer questions like that. If you have any other questions or concerns, feel free to ask.",
    "hi":
        "Hello! How are you today? Is there something I can help you with or would you like to chat?",
    "here":
        "I'm here now. How can I assist you today?",
    "united states":
        "There are 50 states in the United States of America.",
    "today":
        "I'm an AI, I don't have real-time access to the current date. However, I can suggest ways for you to find out the current date.\n\nYou can:\n\n1. Check your device's calendar app.\n2. Look at a physical calendar or planner.\n3. Search online for \"current date\" or use a search engine like Google to find out the current date.\n\nIf you need help with something specific related to dates, feel free to ask, and I'll do my best to assist you!",
    "strawberry":
        "There are 2 \"r\"s and 1 other letter R in the word \"strawberry\"",
    "ping":
        "Pong!",
    "introduction_generic": # generic introduction in case the client asked a model that doesn't have a cached introduction
        "I'm an artificial intelligence model. I can help you with a wide range of tasks, including answering questions, writing content, coding, and more. How can I assist you today?",
    "introduction_llama":
        "I'm an artificial intelligence model known as Llama. Llama stands for \"Large Language Model Meta AI.\"",
    "introduction_gemma":
        "I’m Gemma, a large language model created by the Gemma team at Google DeepMind. I’m an open-weights model, which means I’m widely available for anyone to use. \n\nI’m designed to take text and images as input and produce text as output. I’m still under development, but I can try my best to assist you with a variety of tasks! 😊\n\nWhat can I help you with today?",
    "introduction_qwen":
        "I'm Qwen, an AI assistant developed by Alibaba Cloud. I can help you with a wide range of tasks, including answering questions, writing content, coding, and more. How can I assist you today?",
    "sky blue":
        "The sky appears blue to us because of a phenomenon called Rayleigh scattering. Here's what happens:\n\n1. **Sunlight enters Earth's atmosphere**: When sunlight enters our atmosphere, it encounters tiny molecules of gases such as nitrogen (N2) and oxygen (O2).\n2. **Scattering occurs**: These gas molecules scatter the light in all directions. However, shorter wavelengths of light, like blue and violet, are scattered more than longer wavelengths, like red and orange.\n3. **Blue light is dispersed**: The blue light is scattered in every direction by the tiny molecules, making it visible to our eyes from almost anywhere on a clear day.\n4. **Our eyes perceive the color**: When we look up at the sky, our eyes see the scattered blue light and interpret it as the color blue.\n\nThis phenomenon is named after Lord Rayleigh, who first described it in the late 19th century. The scattering of sunlight by small particles or molecules is known as Rayleigh scattering (not to be confused with Mie scattering, which occurs when larger particles are involved).\n\nOther factors can affect the apparent color of the sky:\n\n* **Atmospheric conditions**: Pollution, dust, and water vapor in the atmosphere can scatter light in different ways, altering the apparent color.\n* **Time of day**: During sunrise and sunset, the sun's rays have to travel through more of the Earth's atmosphere, scattering shorter wavelengths like blue and violet. This is why the sky often appears red or orange during these times.\n* **Cloud cover**: Thick clouds can block or scatter light in ways that change its apparent color.\n\nSo, to summarize: the sky appears blue due to the scattering of sunlight by tiny molecules in our atmosphere, which preferentially scatter shorter wavelengths like blue and violet.",
    "chinese":
        "《霸王别姬》是一部以中国历史题材为背景的爱情电影，改编自宝剑神传《儒林外史》中的一则故事。电影讲述了一个名叫花蝶鸣的人物，他为了保护自己和自己心爱的人免于受到杀害，不得不扮演女装的儒生角色。在以往的历史剧中，这个角色通常由男主角扮演，但在这个电影里，导演陈凯歌选择了一个更为特别的方法：花蝶鸣扮演男孩，这样就避免了在一个已经有女装和男性角色之间的界限上重复使用了类似的符号。\n\n但是，这个角色也是十分有意思的，因为它代表着一个矛盾的东西——表面上看起来像是一个弱女子，但是实际上是非常强大和能够为自己而战的人。这个角色也体现了一个典型的女性心理特征，善良、温柔和自我牺牲。这使得观众们很容易地与花蝙鸣产生共鸣。\n\n但是，这个电影的重点不是花蝙鸣，而是他的爱人。他是一个儒生，在为了保护自己而扮演女装的儒生之后，他又扮演了一个更加危险的角色——扮成妓女。这个角色非常有意思，因为它意味着不仅是在挑战社会性的规范，还在挑战性别的界限。这个妓女扮演者的行为也是十分有趣的地方，虽然她表面上看起来像是一个弱女子，但是实际上是十分强大和能够为自己而战的人。这使得观众们很容易地与她的角色产生共鸣。\n\n但是，这个电影的重点不是花蝙鸣，而是他的爱人。他是一个儒生，在为了保护自己而扮演女装的儒生之后，他又扮演了一个更加危险的角色——扮成妓女。这个角色非常有意思，因为它意味着不仅是在挑战社会性的规范，还在挑战性别的界限。\n\n在电影中，陈凯歌使用了一系列不同的镜头来表现花蝙鸣和他的爱人的关系。这使得观众们能够感受到他们之间的情感联系。例如，在一场舞蹈比赛中，花蝙鸣和他的爱人一起跳舞，这个镜头很好地表现了他们之间的感情联系。\n\n在电影中的一个重要情节中，花蝙鸣为了保护自己和自己的心爱的人不被杀害，他用自己的生命来换取他们的安全。这是一个非常感人的场景，让观众们很容易与他产生共鸣。\n\n但是，这个电影也有一些不足的地方。例如，在一些情节上，它没有表现得足够细致入微，尤其是在展现了花蝙鸣和他的爱人之间的情感联系的时候。这使得观众们感到有些不解。\n\n总的来说，《霸王别姬》是一部很好的电影，它使用了一系列不同的镜头来表现出它强烈的主题。虽然在一些情节上可能存在不足，但是这个电影仍然是一个非常值得一看的作品。"
}