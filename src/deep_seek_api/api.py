import json
import requests


class DeepSeekApi():
    def __init__(self,test_log_handle,config_file):
        self.test_log = test_log_handle
        self.config_file = config_file
        self.url = "https://api.deepseek.com/chat/completions"
        self.headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': 'Bearer'
        }
        self.get_authorization()
        self.payload_dict = {
                  "messages": [
                    {
                      "content": "",
                      "role": "user" }
                  ],
                  "model": "deepseek-chat",
                  "max_tokens": 2048,
                  "response_format": {
                    "type": "text"},
            }
        self.payload = json.dumps(self.payload_dict)
        self.response_text = ""
        self.answer = ""

    def get_authorization(self):
        authorization =  self.config_file.get("deep_seek","api_key")
        self.headers['Authorization'] = 'Bearer '+ authorization
    def ask_question(self,question):
        self.payload_dict["messages"][0]["content"] = question
        self.payload =  json.dumps(self.payload_dict)
        response = requests.request("POST", self.url, headers=self.headers, data=self.payload)
        print(response.text)
        self.response_text =  response.text
    def get_answer(self):
        response_data = json.loads(self.response_text)
        answer = response_data["choices"][0]["message"]["content"]
        return answer








