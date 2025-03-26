from mailjet_rest import Client
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import json

class MailjetService:
    
    @staticmethod
    def send_email(to_email, to_name, subject, template_name, context):
       
        try:
            mailjet = Client(auth=(settings.MAILJET_API_KEY, settings.MAILJET_SECRET_KEY), version='v3.1')
            
            html_content = render_to_string(template_name, context)
            text_content = strip_tags(html_content)
            
            data = {
                'Messages': [
                    {
                        'From': {
                            'Email': 'marten2200@gmail.com',
                            'Name': 'DigiContract'
                        },
                        'To': [
                            {
                                'Email': to_email,
                                'Name': to_name
                            }
                        ],
                        'Subject': subject,
                        'TextPart': text_content,
                        'HTMLPart': html_content
                    }
                ]
            }
            
            result = mailjet.send.create(data=data)
            
            if result.status_code == 200 or result.status_code == 201:
                return True
            else:
                print(f"Mailjet API Error: {result.status_code}")
                print(result.json())
                return False
                
        except Exception as e:
            print(f"Mailjet Service Error: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return False