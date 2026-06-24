from django.db import models


class Wallet(models.Model):
    tg_id = models.CharField(max_length=20, unique=True, db_index=True)
    address = models.CharField(max_length=42, unique=True, db_index=True)
    # Private key encrypted with Fernet (same key as card encryption).
    encrypted_private_key = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"tg:{self.tg_id} → {self.address}"

    @property
    def private_key_hex(self) -> str:
        from config.security import decrypt
        return decrypt(self.encrypted_private_key)

    @private_key_hex.setter
    def private_key_hex(self, value: str) -> None:
        from config.security import encrypt
        self.encrypted_private_key = encrypt(value)
