from django.db import models

# Create your models here.

class ContactFeedback(models.Model):
    email = models.EmailField(max_length=254)
    feedback = models.TextField()
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.email} - {self.submitted_at.strftime('%Y-%m-%d %H:%M')}"
    
    
