#!/usr/bin/env python3
"""Refresh LinkedIn access token when a LINKEDIN_REFRESH_TOKEN is available."""

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ENV_PATH = Path(__file__).with_name('.env')
load_dotenv(dotenv_path=ENV_PATH)

CLIENT_ID = os.getenv('LINKEDIN_CLIENT_ID')
CLIENT_SECRET = os.getenv('LINKEDIN_CLIENT_SECRET')
REFRESH_TOKEN = os.getenv('LINKEDIN_REFRESH_TOKEN')


def mask_token(token):
    if not token:
        return ''
    if len(token) <= 12:
        return token[:4] + '…'
    return token[:8] + '…' + token[-4:]


def set_env_values(path, updates):
    existing = path.read_text().splitlines() if path.exists() else []
    output = []
    remaining = dict(updates)

    for line in existing:
        if '=' in line and not line.lstrip().startswith('#'):
            key = line.split('=', 1)[0].strip()
            if key in remaining:
                value = remaining.pop(key)
                if value is not None:
                    output.append(f'{key}={value}')
                continue
        output.append(line)

    if remaining:
        if output and output[-1] != '':
            output.append('')
        for key, value in remaining.items():
            if value is not None:
                output.append(f'{key}={value}')

    path.write_text('\n'.join(output) + '\n')


def main():
    if not CLIENT_ID or CLIENT_ID == 'your_client_id_here':
        print('❌ ERROR: LINKEDIN_CLIENT_ID not set in .env')
        sys.exit(1)
    if not CLIENT_SECRET or CLIENT_SECRET == 'your_client_secret_here':
        print('❌ ERROR: LINKEDIN_CLIENT_SECRET not set in .env')
        sys.exit(1)
    if not REFRESH_TOKEN:
        print('❌ ERROR: LINKEDIN_REFRESH_TOKEN not set in .env')
        print('Run get_access_token.py and authorize the app. If LinkedIn still does not return a refresh token, this app is not enabled for programmatic refresh tokens.')
        sys.exit(1)

    response = requests.post(
        'https://www.linkedin.com/oauth/v2/accessToken',
        data={
            'grant_type': 'refresh_token',
            'refresh_token': REFRESH_TOKEN,
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
        },
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        timeout=30,
    )

    if response.status_code != 200:
        print(f'❌ ERROR refreshing token: HTTP {response.status_code}')
        print(response.text)
        sys.exit(1)

    token_data = response.json()
    access_token = token_data.get('access_token')
    if not access_token:
        print('❌ ERROR: LinkedIn response did not include access_token')
        print(token_data)
        sys.exit(1)

    set_env_values(ENV_PATH, {
        'LINKEDIN_ACCESS_TOKEN': access_token,
        # LinkedIn may rotate refresh tokens. Preserve the old one if not returned.
        'LINKEDIN_REFRESH_TOKEN': token_data.get('refresh_token') or REFRESH_TOKEN,
        'LINKEDIN_ACCESS_TOKEN_EXPIRES_IN': token_data.get('expires_in'),
        'LINKEDIN_REFRESH_TOKEN_EXPIRES_IN': token_data.get('refresh_token_expires_in'),
        'LINKEDIN_GRANTED_SCOPE': token_data.get('scope'),
    })

    print('✓ LinkedIn access token refreshed and saved to .env')
    print(f'LINKEDIN_ACCESS_TOKEN={mask_token(access_token)}')
    if token_data.get('refresh_token'):
        print(f'LINKEDIN_REFRESH_TOKEN={mask_token(token_data.get("refresh_token"))}')
    if token_data.get('expires_in'):
        print(f'LINKEDIN_ACCESS_TOKEN_EXPIRES_IN={token_data.get("expires_in")}')
    if token_data.get('refresh_token_expires_in'):
        print(f'LINKEDIN_REFRESH_TOKEN_EXPIRES_IN={token_data.get("refresh_token_expires_in")}')
    if token_data.get('scope'):
        print(f'LINKEDIN_GRANTED_SCOPE={token_data.get("scope")}')


if __name__ == '__main__':
    main()
