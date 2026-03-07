import boto3
import uuid
import sys
import time

def get_stack_output(stack_name, output_test):
    client = boto3.client('cloudformation')
    try:
        response = client.describe_stacks(StackName=stack_name)
        outputs = response['Stacks'][0].get('Outputs', [])
        for output in outputs:
            if output['OutputKey'] == output_test:
                return output['OutputValue']
        return None
    except Exception as e:
        print(f"Error getting stack output: {e}")
        return None

def seed_users():
    # DynamoDB Table Name
    table_name = get_stack_output('arrive-users-dev', 'UsersTableName')
    if not table_name:
        print("Could not find UsersTableName in arrive-users-dev stack outputs.")
        sys.exit(1)
        
    # Cognito User Pool ID
    user_pool_id = get_stack_output('arrive-dev', 'UserPoolId')
    if not user_pool_id:
        print("Could not find UserPoolId in arrive-dev stack outputs.")
        sys.exit(1)

    # Restaurants DynamoDB Table Name
    restaurants_table_name = get_stack_output('arrive-restaurants-dev', 'RestaurantsTable') # We might need to look up the actual output key
    
    # If we can't find it easily, we can try to guess or use the known name format if stack output isn't available
    # But better to check stack outputs. Let's assume 'RestaurantsTable' is not an output of 'arrive-restaurants-dev' yet.
    # We might need to query resources or add it to outputs. 
    # Checking previous 'services/restaurants/template.yaml' content (Step 508), it seems `RestaurantsTable` is NOT in Outputs.
    # However, standard naming convention is usually `arrive-restaurants-dev-RestaurantsTable-HASH`.
    # Let's use boto3 to find it or just rely on the seeding script being run where it can find it.
    
    # Actually, let's look at `services/restaurants/template.yaml` again. 
    # It does NOT output the table name.
    # I should update the template to output it, OR I can just look it up by name pattern `arrive-restaurants-dev-RestaurantsTable-*`
    
    # Let's do a lookup.
    
    print(f"Seeding DynamoDB table: {table_name}")
    print(f"Creating users in Cognito User Pool: {user_pool_id}")
    
    dynamodb = boto3.resource('dynamodb')
    users_table = dynamodb.Table(table_name)
    cognito = boto3.client('cognito-idp')
    
    # Find Restaurants Table
    client_ddb = boto3.client('dynamodb')
    response = client_ddb.list_tables()
    restaurants_table_name = None
    for name in response['TableNames']:
        if 'arrive-restaurants-dev-RestaurantsTable' in name:
            restaurants_table_name = name
            break

    # Pre-assign a restaurant ID so it is always defined for the restaurant_admin user below
    test_restaurant_id = str(uuid.uuid4())

    if not restaurants_table_name:
        print("Could not find RestaurantsTable. restaurant_admin will reference an unregistered restaurant.")
    else:
        print(f"Found Restaurants Table: {restaurants_table_name}")
        restaurants_table = dynamodb.Table(restaurants_table_name)

        # Create Test Restaurant
        try:
            restaurants_table.put_item(Item={
                'restaurant_id': test_restaurant_id,
                'name': 'Test Kitchen 1',
                'address': '123 Test St',
                'active': True
            })
            print(f"Created Test Restaurant: Test Kitchen 1 (ID: {test_restaurant_id})")
        except Exception as e:
            print(f"Error creating restaurant: {e}")

    users = [
        {
            'UserId': None, # Will be set to Cognito Sub
            'Email': 'admin@aadi.com',
            'Role': 'admin',
            'Name': 'Super Admin',
            'Password': 'Password123!'
        },
        {
            'UserId': None,
            'Email': 'restaurant@aadi.com',
            'Role': 'restaurant_admin',
            'Name': 'Restaurant Owner',
            'RestaurantId': test_restaurant_id,
            'Password': 'Password123!'
        },
        {
            'UserId': None,
            'Email': 'customer@aadi.com',
            'Role': 'customer',
            'Name': 'Test Customer',
            'Password': 'Password123!'
        }
    ]

    for user in users:
        email = user['Email']
        password = user['Password']
        role = user['Role']
        
        try:
            # 1. Create User in Cognito
            try:
                response = cognito.admin_create_user(
                    UserPoolId=user_pool_id,
                    Username=email,
                    UserAttributes=[
                        {'Name': 'email', 'Value': email},
                        {'Name': 'email_verified', 'Value': 'true'},
                        {'Name': 'custom:role', 'Value': role},
                        {'Name': 'custom:restaurant_id', 'Value': user.get('RestaurantId', '')}
                    ],
                    MessageAction='SUPPRESS' # Don't send welcome email
                )
                user_sub = response['User']['Username']
                print(f"Created Cognito user: {email} (Sub: {user_sub})")
            except cognito.exceptions.UsernameExistsException:
                print(f"User {email} already exists in Cognito. Fetching details...")
                response = cognito.admin_get_user(UserPoolId=user_pool_id, Username=email)
                user_sub = response['Username']
                
                # Update attributes if they exist
                attrs_to_update = [
                    {'Name': 'custom:role', 'Value': role}
                ]
                if 'RestaurantId' in user:
                    attrs_to_update.append({'Name': 'custom:restaurant_id', 'Value': user['RestaurantId']})
                
                cognito.admin_update_user_attributes(
                    UserPoolId=user_pool_id,
                    Username=email,
                    UserAttributes=attrs_to_update
                )
                print(f"Updated attributes for {email}")

            # 2. Set Password
            cognito.admin_set_user_password(
                UserPoolId=user_pool_id,
                Username=email,
                Password=password,
                Permanent=True
            )
            print(f"Set password for {email}")

            # 3. Add to DynamoDB
            item = {
                'UserId': user_sub, # Use Cognito Sub as PK
                'Email': email,
                'Role': role,
                'Name': user['Name']
            }
            if 'RestaurantId' in user:
                item['RestaurantId'] = user['RestaurantId']
            
            users_table.put_item(Item=item)
            print(f"Synced to DynamoDB: {email} (Role: {role})")
            
        except Exception as e:
            print(f"Error processing user {email}: {e}")

if __name__ == '__main__':
    seed_users()
