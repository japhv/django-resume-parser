from rest_framework import serializers
from rest_framework.reverse import reverse

from .models import Resume, ResumeArchive


class ResumeArchiveSerializer(serializers.ModelSerializer):

    class Meta:

        model = ResumeArchive
        fields = ('id', 'uploaded', 'datafile', )


class ResumeSerializer(serializers.ModelSerializer):

    class Meta:
        model = Resume
        fields = ('id', 'name', 'email', 'phone_number', 'area_code', 'street_address',
                  'state', 'zipcode', 'education', 'degree', 'work_history', 'skills')

    def get_links(self, obj):
        request = self.context['request']
        return {
            'self': reverse('api-detail',
                            kwargs={'pk': obj.pk}, request=request),
        }