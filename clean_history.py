#!/usr/bin/env python3
"""
Git history cleaner - Replace sensitive data with placeholders
"""
import sys
import re

def clean_content(content):
    """Replace sensitive data with placeholders"""
    replacements = [
        # Neo4j password
        ('2J07FuTnmvSypqXF7cQQbwNnCVUAr9Fu1RyXRcInx0E', '***REMOVED_NEO4J_PASSWORD***'),
        # Azure API key
        ('88rFcAVHbVq3odpF5GctWjTm7WEi9tgxSHP2dAs8s1uc2a0sA7SbJQQJ99BGACYeBjFXJ3w3AAABACOGJcjN', '***REMOVED_AZURE_API_KEY***'),
        # Neo4j URI
        ('567cbdc0.databases.neo4j.io', '***REMOVED_NEO4J_URI***'),
    ]

    for old, new in replacements:
        content = content.replace(old, new)

    return content

if __name__ == '__main__':
    # Read from stdin
    content = sys.stdin.read()

    # Clean and output
    cleaned = clean_content(content)
    sys.stdout.write(cleaned)
