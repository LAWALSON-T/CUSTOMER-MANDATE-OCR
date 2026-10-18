"""
Generate 1000 sample customers for production testing
"""
import random
from datetime import datetime, timedelta

# Sample data pools
first_names = ["James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda", 
               "William", "Barbara", "David", "Elizabeth", "Richard", "Susan", "Joseph", "Jessica",
               "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
               "Matthew", "Margaret", "Anthony", "Betty", "Mark", "Sandra", "Donald", "Ashley",
               "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle"]

last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
              "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
              "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Thompson", "White",
              "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker", "Young"]

cities = [("New York", "NY"), ("Los Angeles", "CA"), ("Chicago", "IL"), ("Houston", "TX"),
          ("Phoenix", "AZ"), ("Philadelphia", "PA"), ("San Antonio", "TX"), ("San Diego", "CA"),
          ("Dallas", "TX"), ("San Jose", "CA"), ("Austin", "TX"), ("Jacksonville", "FL"),
          ("Fort Worth", "TX"), ("Columbus", "OH"), ("Charlotte", "NC"), ("San Francisco", "CA")]

doc_types = ["passport", "drivers_license", "national_id"]

def generate_sql():
    """Generate SQL INSERT statements for 1000 customers"""
    
    sql_statements = []
    
    for i in range(1, 1001):
        customer_id = f"CUST{i:04d}"  # CUST0001, CUST0002, etc.
        first_name = random.choice(first_names)
        last_name = random.choice(last_names)
        email = f"{first_name.lower()}.{last_name.lower()}{i}@email.com"
        phone = f"+1{''.join([str(random.randint(0,9)) for _ in range(10)])}"
        
        # Random DOB between 1950 and 2000
        dob = datetime(1950, 1, 1) + timedelta(days=random.randint(0, 18250))
        dob_str = dob.strftime('%Y-%m-%d')
        
        # Random address
        street_num = random.randint(100, 9999)
        street_name = random.choice(["Main", "Oak", "Pine", "Maple", "Cedar", "Elm", "Washington"])
        street_type = random.choice(["St", "Ave", "Rd", "Blvd", "Dr"])
        address = f"{street_num} {street_name} {street_type}"
        
        city, state = random.choice(cities)
        postal_code = str(random.randint(10000, 99999))
        
        # Document type
        doc_type = random.choice(doc_types)
        
        # File paths - reuse existing sample files
        sample_num = ((i - 1) % 5) + 1  # Cycle through CUST001-CUST005 files
        id_path = f"/customer_documents/CUST{sample_num:03d}_{doc_type}.jpg"
        address_path = f"/customer_documents/CUST{sample_num:03d}_utility_bill.pdf"
        sig_path = f"/customer_documents/CUST{sample_num:03d}_signature.png"
        
        sql = f"""INSERT INTO customer_mandates (
    customer_id, first_name, last_name, email, phone_number, 
    date_of_birth, address, city, state, country, postal_code,
    id_document_type, id_document_path, proof_of_address_path, signature_path
) VALUES (
    '{customer_id}', '{first_name}', '{last_name}', '{email}', '{phone}',
    '{dob_str}', '{address}', '{city}', '{state}', 'USA', '{postal_code}',
    '{doc_type}', '{id_path}', '{address_path}', '{sig_path}'
);"""
        
        sql_statements.append(sql)
    
    return "\n".join(sql_statements)

if __name__ == "__main__":
    print("Generating SQL for 1000 customers...")
    sql = generate_sql()
    
    # Save to file
    with open("insert_1000_customers.sql", "w") as f:
        f.write(sql)
    
    print(f"✓ Generated insert_1000_customers.sql")
    print(f"✓ Contains 1000 INSERT statements")
    print(f"\nTo load into MySQL:")
    print('docker exec -i mysql_source sh -c "exec mysql -uroot -p$MYSQL_ROOT_PASSWORD customer_db" < insert_1000_customers.sql')