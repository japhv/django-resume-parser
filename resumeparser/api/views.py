from rest_framework import authentication, permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response

from resumeparser.utils import cvparser

from .models import Resume
from .serializers import ResumeSerializer, ResumeArchiveSerializer


class DefaultsMixin(object):
    """ Default settings for view authentication, permissions, filtering and pagination. """

    authentication_classes = (
        authentication.BasicAuthentication,
        authentication.TokenAuthentication,
    )
    permission_classes = (
        permissions.IsAuthenticated,
    )


class ResumeViewSet(DefaultsMixin, ModelViewSet):

    queryset = Resume.objects.all()
    parser_classes = (MultiPartParser, FormParser, )

    def get_serializer_class(self):
        if self.action == 'create':
            return ResumeArchiveSerializer

        return ResumeSerializer

    def perform_create(self, serializer):
        uploaded_file = self.request.data.get('datafile')
        serializer.save(datafile=uploaded_file)

        resume_data = cvparser.process(uploaded_file)
        response_data = resume_data.copy()
        # TODO: Remove after proper DB is added
        if resume_data:
            resume_data['file_id'] = serializer.data['id']
            resume_data['education'] = ', '.join(resume_data['education'])
            resume_data['degree'] = ', '.join(resume_data['degree'])
            resume_data['work_history'] = ''
            # resume_data['work_history'] = ', '.join(resume_data['work_history'])
            resume_data['skills'] = ', '.join(resume_data['skills'])

        resume_serializer = ResumeSerializer(data=resume_data)
        # if resume_serializer.is_valid():
            # resume_serializer.save()

        return response_data

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response_data = self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(response_data, status=status.HTTP_201_CREATED, headers=headers)