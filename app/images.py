import os

from dotenv import load_dotenv
from imagekitio import ImageKit

load_dotenv()

imagekit = ImageKit(
    private_key=os.getenv("IMAGEKIT_PRIVATE_KEY")
)

# El URL_ENDPOINT se guarda como variable aparte para usarlo donde sea necesario
URL_ENDPOINT = os.getenv("IMAGEKIT_URL_ENDPOINT")