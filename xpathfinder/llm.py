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
                f'When responding, output a JSON object with optional keys: "xpath" (new XPath), '
                f'"code" (Python snippet), and "text" (plain-text advice). Do not format the response as markdown.'
                f'If there is no advice other than to apply the XPath or code, no text advice should be given. '
                f'When generating Xpath, correctly apply the default namespace to elements in the namespace `{ns}`. '
                f'When generating Python code, use the `lxml` library for XML processing and make use of: '
                f'`lxml.etree` is already imported as `etree`, `doc` is the current XML document, `xpath_expr` '
                f'is the last XPath, `xpath_result` is the last XPath query result, and `nsmap` is the '
                f'appropriate value for namespaces in queries and methods. Make use of the variables as needed. '
                f'Be concise and precise in your responses.'
            )
        }
        xml_snip = context.get('xml', '')
        xpath_snip = context.get('xpath', '')
        code_snip = context.get('code', '')

        # Construct user content with literal '\n' escapes
        user_content = (
            'Context:\n'
            f'XML Document:\n```xml\n{xml_snip}\n```\n'
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
