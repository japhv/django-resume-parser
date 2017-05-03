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
        if uploaded_file.name.endswith('docx'):
            raw_text = cvparser.convert_docx_to_txt(uploaded_file)
        else:
            raw_text = cvparser.convert_pdf_to_txt(uploaded_file)
        resume = {
            'name': cvparser.extract_name(raw_text),
            'email': cvparser.exract_email(raw_text),
            'phone_number': cvparser.extract_phone_number(raw_text),
            'street_address': cvparser.extract_address(raw_text),
            'state': cvparser.extract_state(raw_text),
            'zipcode': cvparser.extract_zip(raw_text),
            'education': ', '.join(cvparser.extract_edu_info(raw_text)),
            'degree': ', '.join(cvparser.extract_degree_info(raw_text)),
            'work_history': ', '.join(cvparser.extract_company_info(raw_text)),
            'skills': ', '.join(cvparser.extract_skills(raw_text)),
            'file_id': serializer.data['id']
        }
        resume_serializer = ResumeSerializer(data=resume)
        if resume_serializer.is_valid():
            resume_serializer.save()

        return resume_serializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resume_serializer = self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(resume_serializer.data, status=status.HTTP_201_CREATED, headers=headers)