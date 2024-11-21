import requests
import os
from glueops import setup_logging
import traceback

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logger = setup_logging.configure(level=LOG_LEVEL)

class GetOutlineClient:
    """
    A client to interact with the Outline API for managing documents.
    """

    def __init__(self, api_url, document_id, api_token):
        """
        Initializes the GetOutlineClient with the necessary API credentials.

        :param api_url: The base URL for the Outline API.
        :param document_id: The ID of the document to manage.
        :param api_token: The API token for authentication.
        """
        self.api_url = api_url.rstrip('/')  # Ensure no trailing slash
        self.document_id = document_id
        self.api_token = api_token
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_token}"
        }

    def update_document(self, markdown_text):
        """
        Updates the content of the specified document with new markdown text.

        :param markdown_text: The new markdown text to update the document with.
        """
        logger.debug("Updating document on Outline.")
        url = f"{self.api_url}/api/documents.update"
        payload = {
            "id": self.document_id,
            "text": markdown_text
        }

        try:
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            logger.info(f"Document update response code: {response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error updating document: {e}")
            logger.error(traceback.format_exc())
            raise

    def get_document_uuid(self):
        """
        Retrieves the UUID of the parent document.

        :return: The UUID of the parent document or None if an error occurs.
        """
        url = f"{self.api_url}/api/documents.info"
        payload = {
            "id": self.document_id
        }

        try:
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            parent_id = response.json().get("data", {}).get("id")
            logger.debug(f"Parent document UUID: {parent_id}")
            return parent_id
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting parent document UUID: {e}")
            logger.error(traceback.format_exc())
            raise


    def get_children_documents_to_delete(self, parent_document_id):
        """
        Retrieves a list of child document IDs under the specified parent document.

        :param parent_document_id: The UUID of the parent document.
        :return: A list of child document IDs.
        """
        url = f"{self.api_url}/api/documents.list"
        payload = {
            "parentDocumentId": parent_document_id,
            "limit": 1,
            "offset": 0
        }
        all_ids = []

        try:
            while True:
                response = requests.post(url, json=payload, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                child_docs = data.get("data", [])
                new_ids = [doc.get("id") for doc in child_docs if "id" in doc]
                all_ids.extend(new_ids)
                
                # Check if there is a next page
                pagination = data.get("pagination", {})
                next_path = pagination.get("nextPath")
                if len(new_ids) == 0 or not next_path:
                    break
                
                # Update the payload for the next request
                payload["offset"] += payload["limit"]

            logger.debug(f"Child document IDs to delete: {all_ids}")
            return all_ids
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting children documents: {e}")
            logger.error(traceback.format_exc())
            raise


    def delete_document(self, document_id):
        """
        Deletes a document with the specified document ID.

        :param document_id: The ID of the document to delete.
        :return: True if deletion was successful, False otherwise.
        """
        url = f"{self.api_url}/api/documents.delete"
        payload = {
            "id": document_id
        }

        try:
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            logger.debug(f"Successfully deleted document with ID: {document_id}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Error deleting document {document_id}: {e}")
            logger.error(traceback.format_exc())
            raise


    def create_document(self, parent_document_id, title, text):
        """
        Creates a new document under the specified parent document.

        :param parent_document_id: The UUID of the parent document.
        :param title: The title of the new document.
        :param text: The markdown text content of the new document.
        :return: True if creation was successful, False otherwise.
        """
        url = f"{self.api_url}/api/documents.create"
        payload = {
            "parentDocumentId": parent_document_id,
            "title": title,
            "text": text,
            "publish": True
        }

        try:
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            logger.info(f"Successfully created document with title: {title}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating document '{title}': {e}")
            logger.error(traceback.format_exc())
            raise

