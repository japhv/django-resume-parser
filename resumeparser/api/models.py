from django.db import models

from resumeparser.utils import validator


# Create your models here.
class ResumeArchive(models.Model):

    uploaded = models.DateTimeField(auto_now_add=True)
    datafile = models.FileField(upload_to='resumes/%Y/%m/%d', validators=[validator.validate_file_extension])


# Create your models here.
class Resume(models.Model):

    name = models.CharField(max_length=70)
    email = models.CharField(max_length=254)
    phone_number = models.CharField(max_length=26)
    area_code = models.CharField(max_length=3)
    street_address = models.CharField(max_length=90)
    state = models.CharField(max_length=20)
    zipcode = models.CharField(max_length=11)
    education = models.TextField()
    degree = models.TextField(default='')
    work_history = models.TextField()
    skills = models.TextField(default='')
    file_id = models.ForeignKey(ResumeArchive, default='null')

    def __str__(self):
        return self.name