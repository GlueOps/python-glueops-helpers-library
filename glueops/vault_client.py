import requests


class RedirectError(Exception):
    """Received a redirect response when trying to read a secret from Vault.
    You are probably using pomerium or something went wrong in cluster and your token expired.
    """
    pass

def vault_response_handler(vault_api_call):
    def wrapper(*args, **kwargs):
        response = vault_api_call(*args, **kwargs)
        if response.headers.get('Location'):
            raise RedirectError(
                "Received a redirect response when trying to read a secret from Vault. "
                "Possible reasons: using pomerium, cluster issues, or token expired."
            )
        if not response.ok:
            raise Exception(f"Error from Secret Store: {response.status_code}")
        try:
            response_data = response.json()
            return response_data
        except ValueError:
            raise Exception("Unexpected response format from Secret Store.")
    return wrapper


class VaultClient:
    def __init__(
        self,
        vault_url: str,
        kubernetes_role: str,
        vault_token: str = None,
        pomerium_cookie: str = None
    ) -> None:
        """
        Initialize a VaultClient for reading and writing secrets to vault.

        :param vault_url: The url of the target vault cluster
        :param kubernetes_role: The kubernetes_role to use when generating an client toke to access vault.
        :param vault_token: The vault token to use for accessing vault and can be generated in this class.
        :param pomerium_cookie: Pomerium's cookie to use to access vault.  Retrieved from a browser session that has been authenticated to vault.
        """
        self.vault_url = vault_url
        self.kubernetes_role = kubernetes_role
        self.vault_token = vault_token
        self.pomerium_cookie = pomerium_cookie

    def _get_jwt_token(self) -> str:
        with open('/var/run/secrets/kubernetes.io/serviceaccount/token', 'r') as f:
            return f.read().strip()

    def _get_vault_token_via_kube_auth(self) -> str:
        jwt_token = self._get_jwt_token()
        payload = {
            "jwt": jwt_token,
            "role": self.kubernetes_role
        }
        response = requests.post(
            f"{self.vault_url}/v1/auth/kubernetes/login",
            json=payload,
            verify=False
        )
        response.raise_for_status()

        return response.json()["auth"]["client_token"]

    def _adjust_path(self, path: str) -> str:
        if path.startswith("secret/") and not path.startswith("secret/data/"):
            return path.replace("secret/", "secret/data/")
        return path

    def _vault_auth(self):
        if not self.vault_token:
            self.vault_token = self._get_vault_token_via_kube_auth()
        self.headers = {
            'X-Vault-Token': self.vault_token
        }
        if self.pomerium_cookie:
            self.headers["cookie"] = f"_pomerium={self.pomerium_cookie}"

    @vault_response_handler
    def _query_vault(
        self,
        secret_path: str
    ):
        self._vault_auth()

        secret_path = self._adjust_path(secret_path)

        return requests.get(
            f"{self.vault_url}/v1/{secret_path}",
            headers=self.headers,
            verify=False,
            allow_redirects=False
        )

    def get_data_from_vault(
        self,
        secret_path: str
    ):
        self._vault_auth()
        response_data = self._query_vault(
            secret_path=secret_path
        )
        if 'data' not in response_data:
            raise Exception("Missing data.")

        actual_data = response_data['data'].get('data')
        if not actual_data:
            raise Exception("Failed to get secret from secret store")

        return actual_data


    @vault_response_handler
    def write_data_to_vault(
        self,
        secret_path: str,
        data: dict
    ):
        self._vault_auth()

        secret_path = self._adjust_path(secret_path)

        write_vault_path=f"{self.vault_url}/v1/{secret_path}"
        response = requests.post(
            write_vault_path,
            headers=self.headers,
            verify=False,
            allow_redirects=False,
            json={"data":data}
        )
        return response
