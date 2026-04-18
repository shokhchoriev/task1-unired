from django.db import models

# Create your models here.
class Card(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('expired', 'Expired'),
    ]

    card_number = models.CharField(max_length=16)
    expire = models.CharField(max_length=15)
    phone = models.CharField(max_length=20, blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    balance = models.DecimalField(max_digits=15, decimal_places=2)

    def __str__(self):
        return self.card_number
    


    def formatted_card_number(self):
        num = self.card_number.replace(" ", "")
        return " ".join([num[i:i+4] for i in range(0, len(num), 4)])

    def formatted_phone(self):
        if not self.phone:
            return "No phone"

        digits = ''.join(filter(str.isdigit, self.phone))

        if len(digits) == 9:
            return f"+998 {digits[:2]} {digits[2:5]} {digits[5:7]} {digits[7:]}"
        return self.phone