import os
import json
import win32cred
from openai import OpenAI
from typing import Union

class LLMClient:
    """
    A modern OpenAI ChatGPT client for generating XPath expressions and Python code.
    Always returns a dict with optional keys: 'xpath', 'code', 'text'.
    """
    def __init__(self, api_key=None, model='gpt-3.5-turbo', **client_kwargs):
        self.api_key = api_key or retrieve_api_key('OpenAI API Key')
        self.api_key_env = False
        if not self.api_key:
            self.api_key = os.getenv('OPENAI_API_KEY')
            self.api_key_env = True
        # Initialize new OpenAI client
        self.client = OpenAI(api_key=self.api_key, **client_kwargs)
        self.model = model

    def query(self, prompt: str, context: dict, ns: str) -> dict:
        # Build messages as plain dicts
        system_msg = {
            'role': 'system',
            'content': (
                f'You are an expert assistant specialized in XML, XPath, and Python scripting. '
                f'The request includes a User Query, XML Structure describing the structure of the current document, '
                f'XML sample as a sample of the xml data (if too large to include entirely), Current XPath with the '
                f'most recent XPath expression, and Current Code with the most recent Python code. '
                f'When responding, output a JSON object with optional keys: "xpath" (new XPath), '
                f'"code" (Python snippet), and "text" (plain-text advice to the user). '
                f'Do not format the response as markdown. '
                f'If there is no advice other than to apply the XPath or code, no text advice should be given. '
                f'When generating Xpath, apply the default namespace to elements in the namespace `{ns}` where needed. '
                f'When generating Python code, use the `lxml` library for XML processing and remember: '
                f'`lxml.etree` is already imported as `etree`, `doc` contains a reference to the current XML document, '
                f'`xpath_expr` contains the last XPath, `xpath_result` contains the last XPath query result, '
                f'and `nsmap` contains a dict to be used `namespaces` in queries and methods. '
                f'Make use of these variables as needed. '
                f'Only create local files when specifically requested, otherwise generate text output from Python. '
                f'Be concise and precise in your responses, using the most idiomatic XPath and Python.'
            )
        }
        xml_structure = context.get('xml_structure', '')
        xml_sample = context.get('xml_sample', '')
        xpath_snip = context.get('xpath', '')
        code_snip = context.get('code', '')

        # Construct user content with literal '\n' escapes
        user_content = (
            'Context:\n'
            f'XML Structure:\n```\n{xml_structure}\n```\n'
            f'XML Sample:\n```xml\n{xml_sample}\n```\n'
            f'Current XPath:\n```xpath\n{xpath_snip}\n```\n'
            f'Current Code:\n```python\n{code_snip}\n```\n'
            f'User Query:\n{prompt}'
        )
        user_msg = {'role': 'user', 'content': user_content}

        # Call new API
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[system_msg, user_msg]
        )

        raw = response.choices[0].message.content.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {'text': raw}


def store_api_key(target_name: str, api_key_value: str) -> None:
    credential = {
        'Type': win32cred.CRED_TYPE_GENERIC,
        'TargetName': target_name,
        'CredentialBlob': api_key_value,
        'Persist': win32cred.CRED_PERSIST_LOCAL_MACHINE
    }
    win32cred.CredWrite(credential, 0)


def retrieve_api_key(target_name: str) -> Union[str, None]:
    try:
        credential = win32cred.CredRead(target_name, win32cred.CRED_TYPE_GENERIC, 0)
        return credential['CredentialBlob'].decode('utf16')
    except (NameError, Exception) as e:
        if isinstance(e, NameError) or (hasattr(e, 'funcname') and e.funcname == 'CredRead'):
            return None
        raise e


def delete_api_key(target_name: str) -> None:
    try:
        win32cred.CredDelete(target_name, win32cred.CRED_TYPE_GENERIC, 0)
    except NameError:
        pass
