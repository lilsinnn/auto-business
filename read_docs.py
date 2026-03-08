import requests
from bs4 import BeautifulSoup

url = "https://yandex.cloud/ru/docs/search-api/operations/search"
r = requests.get(url)
soup = BeautifulSoup(r.text, "html.parser")
for pre in soup.find_all("pre"):
    print(pre.text)
