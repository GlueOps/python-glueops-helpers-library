import os
import glueops.setup_logging
import kubernetes

logger = glueops.setup_logging.configure(level=os.environ.get('LOG_LEVEL', 'INFO'))

def load_kubernetes_config(logger):
    try:
        if os.getenv('KUBERNETES_SERVICE_HOST'):
            logger.info("KUBERNETES_SERVICE_HOST has a value so we must be running inside of kubernetes")
            logger.info('Attempting to load in-cluster Kubernetes configuration')
            kubernetes.config.load_incluster_config()
        else:
            logger.info('Using local Kubeconfig because we are not running in kubernetes')
            kubernetes.config.load_kube_config()
        logger.info('Successfully loaded Kubernetes configuration')
    except kubernetes.config.ConfigException as e:
        logger.error(f'Kubernetes configuration error: {e}')
        os.sys.exit('Failed to load Kubernetes configuration, exiting application')

    try:
        v1 = kubernetes.client.CoreV1Api()
        custom_api = kubernetes.client.CustomObjectsApi()
        return v1, custom_api
    except Exception as e:
        logger.error(f'Error setting up Kubernetes API clients: {e}')
        os.sys.exit('Failed to setup Kubernetes API clients, exiting application')
