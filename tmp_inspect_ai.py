from google.cloud import aiplatform_v1
import inspect
print('IndexEndpointServiceClient has match:', hasattr(aiplatform_v1.IndexEndpointServiceClient, 'match'))
print('MatchServiceClient has find_neighbors:', hasattr(aiplatform_v1.MatchServiceClient, 'find_neighbors'))
print('IndexEndpointServiceClient.match signature:', inspect.signature(aiplatform_v1.IndexEndpointServiceClient.match) if hasattr(aiplatform_v1.IndexEndpointServiceClient, 'match') else 'n/a')
print('MatchServiceClient.find_neighbors signature:', inspect.signature(aiplatform_v1.MatchServiceClient.find_neighbors) if hasattr(aiplatform_v1.MatchServiceClient, 'find_neighbors') else 'n/a')
