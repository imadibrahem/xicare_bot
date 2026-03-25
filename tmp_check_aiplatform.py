import google.cloud.aiplatform_v1 as aip
import inspect
print('aiplatform_v1 version:', getattr(aip, '__version__', 'n/a'))
print('aiplatform_v1 file:', aip.__file__)
print('MatchServiceClient exists:', hasattr(aip, 'MatchServiceClient'))
print('IndexEndpointServiceClient exists:', hasattr(aip, 'IndexEndpointServiceClient'))
print('IndexEndpointServiceClient.match exists:', hasattr(aip.IndexEndpointServiceClient, 'match'))
print('MatchServiceClient.find_neighbors exists:', hasattr(aip.MatchServiceClient, 'find_neighbors'))
print('MatchServiceClient.find_neighbors signature:', inspect.signature(aip.MatchServiceClient.find_neighbors))
