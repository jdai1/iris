import { Box, VStack, Card, CardBody, Text, Heading, Spinner, Link, Button } from '@chakra-ui/react';
import React, { useState, useEffect } from 'react';
import { Link as RouterLink } from 'react-router-dom';

interface Author {
  name: string;
  blog: string;
  count: number;
}

const Authors: React.FC = () => {
  const [authors, setAuthors] = useState<Author[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchAuthors = async () => {
      try {
        const response = await fetch('http://127.0.0.1:5000/api/authors');
        if (!response.ok) {
          throw new Error('Failed to fetch authors');
        }
        const authors = await response.json();
        console.log(authors)
        setAuthors(authors);
      } catch (error) {
        console.error('Error fetching authors:', error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchAuthors();
  }, []);

  if (isLoading) {
    return (
      <Box display="flex" justifyContent="center" mt={8}>
        <Spinner size="xl" color="brand.600" />
      </Box>
    );
  }

  return (
    <Box pt="3vh" px={4} maxW="800px" mx="auto">
      <VStack spacing={4} align="stretch">
        {authors.map((author, index) => (
          <Card key={index} variant="outline">
            <CardBody>
              <Text fontSize="lg" fontWeight="bold" color="brand.600">
                {author.name}
              </Text>
              <Text color="gray.600" mt={1}>
                {author.blog}
              </Text>
              <Text mt={2}>
                {author.count} {author.count === 1 ? 'article' : 'articles'}
              </Text>
            </CardBody>
          </Card>
        ))}
      </VStack>
    </Box>
  );
};

export default Authors;
