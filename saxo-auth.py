import requests

class OAuth2Client:
    def __init__(self, client_id, client_secret, redirect_uri, auth_endpoint, token_endpoint):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.auth_endpoint = auth_endpoint
        self.token_endpoint = token_endpoint
    def _get_auth_url(self, **params):
        default_params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri
        }
        default_params.update(params)
        return self.auth_endpoint + '?' + '&'.join(f"{k}={v}" for k, v in default_params.items())
    def _exchange_for_token(self, code):
        return requests.post(self.token_endpoint, data={
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'redirect_uri': self.redirect_uri
        }).json()


def handle_oauth_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            return {"error": str(e)}
    return wrapper

class AuthorizationCodeClient(OAuth2Client):
    @handle_oauth_errors
    def get_authorization_url(self, **params):
        return self._get_auth_url(response_type='code', **params)
    @handle_oauth_errors
    def get_token(self, code):
        return self._exchange_for_token(code)


# Implicit flow
class ImplicitClient(OAuth2Client):
    @handle_oauth_errors
    def get_authorization_url(self, **params):
        return self._get_auth_url(response_type='token', **params)


class ClientCredentialsClient(OAuth2Client):
    @handle_oauth_errors
    def get_token(self):
        response = requests.post(self.token_endpoint, data={
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'client_credentials'
        })
        return response.json()

# Define your OAuth2 client
client = ImplicitClient(
    client_id="c310e92ffc7c481190119ea98c507a2e",
    client_secret="67f8314ea810459e8ddc725a4cfd5568",
    redirect_uri="http://gttkeith.github.io/python-saxo/authcode",
    auth_endpoint="https://sim.logonvalidation.net/authorize",
    token_endpoint="https://sim.logonvalidation.net/token"
)

# Get the authorization URL and redirect the user
auth_url = client.get_authorization_url(scope="required_scope")
print(f"Redirect the user to: {auth_url}")

# After redirect, exchange the code for a token
code = "RECEIVED_CODE"
#token_info = client.get_token(code)
#print(token_info)
