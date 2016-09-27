#!/usr/bin/env python

import os
import sys
import time
import json
import boto3
import logging
from mimetypes import MimeTypes
reload(sys)
sys.setdefaultencoding('utf8')

# Initializing logging
scriptLogger = logging.getLogger()
scriptLogger.setLevel(logging.INFO)
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
scriptLogger.addHandler(ch)

apiStackName = os.environ['bamboo_hipchat_statuspage_api_stack_name']
apiGWRestName = os.environ['bamboo_hipchat_statuspage_api_rest_name']
apiStageName = os.environ['bamboo_hipchat_statuspage_api_stage_name']
fileCFName = os.environ['bamboo_hipchat_statuspage_file_cf_name']
tempFileCFName = 'CloudFormation.template'
apiKey = os.environ['bamboo_hipchat_statuspage_api_key']
apiPageId = os.environ['bamboo_hipchat_statuspage_api_page_id']
awsAccessKey = os.environ['bamboo_hipchat_aws_devops_access_key']
awsSecretKey = os.environ['bamboo_hipchat_aws_devops_password']
awsRegion = os.environ['bamboo_hipchat_statuspage_aws_region_name']
awsBacketName = os.environ['bamboo_hipchat_statuspage_aws_backet_name']
dirStaticContent = os.environ['bamboo_hipchat_statuspage_dir_static_content']

paramStack = [{'ParameterKey': 'APIGWRestName', 'ParameterValue': apiGWRestName},
              {'ParameterKey': 'APIStageName',  'ParameterValue': apiStageName},
              {'ParameterKey': 'AWSRegion',     'ParameterValue': awsRegion},
              {'ParameterKey': 'APIKEY',        'ParameterValue': apiKey},
              {'ParameterKey': 'PAGEID',        'ParameterValue': apiPageId},
              {'ParameterKey': 'S3BucketName',  'ParameterValue': awsBacketName}
              ]

try:
    command = sys.argv[1]
except IndexError:
    command = None


# exceptions
def oops(msg):
  scriptLogger.error(msg)
  raise
  sys.exit(1)

# cf connector
def ConnectorAWS(type):
    try:
        global client
        client = boto3.client(type, aws_access_key_id=awsAccessKey,
                              aws_secret_access_key=awsSecretKey, region_name=awsRegion)
    except:
        oops('Can\'t connect to AWS ')


def Deploy():
    ConnectorAWS('cloudformation')
    if ExistingCfStack() and ValidateCfFile(tempFileCFName):
        UpdateCfStack(tempFileCFName)
    else:
        if ValidateCfFile(tempFileCFName):
            CreateCfStack(tempFileCFName)


def CreateCfStack(fileName):
    with open(fileName, 'r') as f:
        try:
            response = client.create_stack(StackName=apiStackName,
                                       TemplateBody=f.read(),
                                       Capabilities=['CAPABILITY_IAM'],
                                       Parameters=paramStack
                                       )
            scriptLogger.info('Start creating.')
            scriptLogger.info('The stack ' + apiStackName +
                              ' is being created... ')
            while True:
                stack = client.describe_stacks(StackName=apiStackName)
                env = stack.get('Stacks')
                if env[0].get('StackStatus') != 'CREATE_IN_PROGRESS':
                    scriptLogger.info(env[0].get('StackStatus'))
                    break
                scriptLogger.info(env[0].get('StackStatus'))
                time.sleep(30)
            waiter = client.get_waiter('stack_create_complete')
            waiter.wait(StackName=apiStackName)
            scriptLogger.info('The stack ' + apiStackName +
                              ' created complete ')
            GetCloudFrontDomain()
        except:
            oops('Can\'t create stack: ' + apiStackName)


def UpdateCfStack(fileName):
    with open(fileName, 'r') as f:
        try:
            response = client.update_stack(StackName=apiStackName,
                                       TemplateBody=f.read(),
                                       Capabilities=['CAPABILITY_IAM'],
                                       Parameters=paramStack
                                       )
            scriptLogger.info('Start updating.')
            scriptLogger.info('The stack ' + apiStackName +
                              ' is beging updated... ')
            while True:
                stack = client.describe_stacks(StackName=apiStackName)
                env = stack.get('Stacks')
                if env[0].get('StackStatus') != 'UPDATE_IN_PROGRESS':
                    scriptLogger.info(env[0].get('StackStatus'))
                    break
                scriptLogger.info(env[0].get('StackStatus'))
                time.sleep(5)
            waiter = client.get_waiter('stack_update_complete')
            waiter.wait(StackName=apiStackName)
            scriptLogger.info('The stack ' + apiStackName +
                              ' updated complete ')
        except:
            if CompareTemplate():
                 scriptLogger.info(apiStackName +
                          ' cloudformation stack has not been changed')
            else:
                 oops('Can\'t update stack: ' + apiStackName)


def ValidateCfFile(fileName):
    with open(fileName, 'r') as f:
        try:
            response = client.validate_template(TemplateBody=f.read())
            scriptLogger.info('Validate cf script is OK.')
            return 1
        except:
            oops('Validate cf script ERROR.')


def ExistingCfStack():
    try:
        response = client.list_stack_resources(StackName=apiStackName)
        scriptLogger.info('Stack already exists.')
        return 1
    except:
        scriptLogger.info('Not exists ' + apiStackName +
                          ' cloudformation stack')


def CompareTemplate():
    ConnectorAWS('cloudformation')
    code_template = client.get_template(StackName=apiStackName)
    file = open(tempFileCFName, 'r')
    code_file = json.loads(file.read())
    if code_template['TemplateBody'] == code_file:
       return 1


def ReplaceLineInFile(fileName):
    text = []
    file = open(fileName, 'r')

    for line in file.readlines():
        line = (line.replace(u'\u2002', ' '))
        if line.find('var PAGE_ID') == 0:
            text.append('\t\t\"%s\",\"\\n\",\n' % (
                ('var PAGE_ID=\'\", {\"Ref\": \"PAGEID\"}, \"\';').rstrip('\n')))
        elif line.find('var API_KEY') == 0:
            text.append('\t\t\"%s\",\"\\n\",\n' % (
                ('var API_KEY=\'\", {\"Ref\": \"APIKEY\"}, \"\';').rstrip('\n')))
        else:
            text.append('\t\t\"%s\",\"\\n\",\n' %
                        (line.replace('\"', '\\" ').rstrip('\n')))

    return ''.join(text)[0:-2]
    file.close()


def PreFile(fileName):
    file = open(fileName, 'r')
    w = open(tempFileCFName, 'w')

    for line in file.readlines():
        if '%COMPONENTSFUNC%' in line:
            w.write(ReplaceLineInFile('lambda/Components.js'))
        elif '%INCIDENTSFUNC%' in line:
            w.write(ReplaceLineInFile('lambda/Incidents.js'))
        elif '%SUBSCRIBERSFUNC%' in line:
            w.write(ReplaceLineInFile('lambda/Subscribers.js'))
        else:
            w.write(str(line))
    scriptLogger.info('File created successfully ')
    w.close()
    file.close()


def GetAPIID():
    ConnectorAWS('cloudformation')
    scriptLogger.info('Getting apiID...')
    try:
        describe_stacks_result = client.describe_stacks(StackName=apiStackName)
        apiID = describe_stacks_result.get('Stacks')[0].get('Outputs')[0].get('OutputValue')
        return apiID
        scriptLogger.info('APIGwRestApi is: ' + apiID)
    except:
        oops('Unable to get API CloudFormation stack!')


def GetCloudFrontDomain():
    ConnectorAWS('cloudformation')
    scriptLogger.info('Getting CloudFrontDomain ...')
    try:
        describe_stacks_result = client.describe_stacks(StackName=apiStackName)
        CFrontDomainName = describe_stacks_result.get('Stacks')[0].get('Outputs')[2].get('OutputValue')
        return CFrontDomainName
        scriptLogger.info('CloudFront Domain is: ' + CFrontDomainName)
    except:
        oops('Unable to get CFrontDomainName CloudFormation stack!')


def SetEndpointIDtoFile():
    apiID = GetAPIID()
    scriptLogger.info('Modifying endpoints.js file inserting the Api gateway ID')
    try:
        os.remove(dirStaticContent + '/js/endpoints.js')
    except OSError:
        pass

    replacements = {
        '$incidentsTemplateURL$': 'https://' + apiID + '.execute-api.' + awsRegion + '.amazonaws.com/' + apiStageName + '/api/incidents',
        '$componentsTemplateURL$': 'https://' + apiID + '.execute-api.' + awsRegion + '.amazonaws.com/' + apiStageName + '/api/components',
        '$subscribersTemplateURL$': 'https://' + apiID + '.execute-api.' + awsRegion + '.amazonaws.com/' + apiStageName + '/api/subscribers',
    }

    with open(dirStaticContent + '/js/endpoints.template') as infile, open(dirStaticContent + '/js/endpoints.js', 'w') as outfile:
        for line in infile:
            for src, target in replacements.iteritems():
                line = line.replace(src, target)
            outfile.write(line)

    infile.close()
    outfile.close()


def PutToS3Static(local_directory, bucket_name):
    ConnectorAWS('s3')

    # enumerate local files recursively
    for root, dirs, files in os.walk(local_directory):
        for filename in files:
            local_path = os.path.join(root, filename)
            relative_path = os.path.relpath(local_path, local_directory)
            mime = MimeTypes()
            mime_type = mime.guess_type(local_path)
            file = open(local_path, 'r')
            data = file.read()
            if mime_type[0]  is not None:
                mime_type = mime_type[0]
            else:
                mime_type = 'application/octet-stream'

            scriptLogger.info("Uploading %s..." % local_path + mime_type)
            client.put_object(Body=data, Bucket=bucket_name, Key=relative_path,
                              ACL='public-read', StorageClass='STANDARD', ContentType=mime_type)
    scriptLogger.info("You can use cloudfront domain name " + GetCloudFrontDomain())


# main
if __name__ == '__main__':
    if command == 'deploy':
        Deploy()
    elif command == 'prepare-cf-file':
        PreFile(fileCFName)
    elif command == 'prepare-endpoint-file':
        SetEndpointIDtoFile()
    elif command == 'copy-to-s3':
        PutToS3Static(dirStaticContent, awsBacketName)
    else:
        print('usage: StatusPage-Deployment-new.py --help \nerror: incorrect number of arguments')
