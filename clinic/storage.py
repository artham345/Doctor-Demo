from django.core.files.storage import FileSystemStorage
from django.core.exceptions import ValidationError

class DisabledUploadStorage(FileSystemStorage):
    def _save(self, name, content):
        raise ValidationError('Configure durable S3 media storage before uploading a photo in production.')
