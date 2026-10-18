-- Create customer_mandates table
CREATE TABLE IF NOT EXISTS customer_mandates (
    customer_id VARCHAR(50) PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL,
    phone_number VARCHAR(20),
    date_of_birth DATE,
    address TEXT,
    city VARCHAR(100),
    state VARCHAR(100),
    country VARCHAR(100),
    postal_code VARCHAR(20),
    id_document_type VARCHAR(50),  -- e.g., 'passport', 'drivers_license', 'national_id'
    id_document_path VARCHAR(500),  -- Path to ID document (PDF or image)
    proof_of_address_path VARCHAR(500),  -- Path to proof of address document
    signature_path VARCHAR(500),  -- Path to signature image
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'pending'  -- pending, processed, failed
);

-- Create index for faster queries
CREATE INDEX idx_status ON customer_mandates(status);
CREATE INDEX idx_created_at ON customer_mandates(created_at);

-- Insert sample data
INSERT INTO customer_mandates (
    customer_id, first_name, last_name, email, phone_number, 
    date_of_birth, address, city, state, country, postal_code,
    id_document_type, id_document_path, proof_of_address_path, signature_path
) VALUES 
(
    'CUST001',
    'John',
    'Doe',
    'john.doe@email.com',
    '+1234567890',
    '1985-06-15',
    '123 Main Street, Apt 4B',
    'New York',
    'NY',
    'USA',
    '10001',
    'passport',
    '/customer_documents/CUST001_passport.pdf',
    '/customer_documents/CUST001_address_proof.pdf',
    '/customer_documents/CUST001_signature.png'
),
(
    'CUST002',
    'Jane',
    'Smith',
    'jane.smith@email.com',
    '+1234567891',
    '1990-03-22',
    '456 Oak Avenue',
    'Los Angeles',
    'CA',
    'USA',
    '90001',
    'drivers_license',
    '/customer_documents/CUST002_drivers_license.jpg',
    '/customer_documents/CUST002_utility_bill.pdf',
    '/customer_documents/CUST002_signature.jpg'
),
(
    'CUST003',
    'Robert',
    'Johnson',
    'robert.j@email.com',
    '+1234567892',
    '1988-11-30',
    '789 Pine Road',
    'Chicago',
    'IL',
    'USA',
    '60601',
    'national_id',
    '/customer_documents/CUST003_national_id.png',
    '/customer_documents/CUST003_bank_statement.pdf',
    '/customer_documents/CUST003_signature.png'
),
(
    'CUST004',
    'Emily',
    'Williams',
    'emily.w@email.com',
    '+1234567893',
    '1992-07-18',
    '321 Elm Street',
    'Houston',
    'TX',
    'USA',
    '77001',
    'passport',
    '/customer_documents/CUST004_passport.pdf',
    '/customer_documents/CUST004_lease_agreement.pdf',
    '/customer_documents/CUST004_signature.jpg'
),
(
    'CUST005',
    'Michael',
    'Brown',
    'michael.b@email.com',
    '+1234567894',
    '1987-02-25',
    '654 Maple Drive',
    'Phoenix',
    'AZ',
    'USA',
    '85001',
    'drivers_license',
    '/customer_documents/CUST005_drivers_license.png',
    '/customer_documents/CUST005_utility_bill.jpg',
    '/customer_documents/CUST005_signature.png'
);

-- Display the data
SELECT * FROM customer_mandates;
