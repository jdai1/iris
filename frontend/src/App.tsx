import { Box, Flex, Input, Spinner, VStack, Card, CardBody, Text, Tag, HStack, Link, Heading, Button } from '@chakra-ui/react';
import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Link as RouterLink } from 'react-router-dom';
import Links from './components/Links';

interface SearchResult {
  id: string;
  blog: string;
  name: string;
  summary: string;
  topics: string;
  author: string;
  date: string;
  url: string;
}

const Search: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState<SearchResult[]>([]);

  const performSearch = async (query: string) => {
    setIsLoading(true);
    try {
      const response = await fetch(`http://127.0.0.1:5000/api/search?q=${encodeURIComponent(query)}`);
      if (!response.ok) {
        throw new Error('Search request failed');
      }
      const data = await response.json();
      setResults(data["results"]);
    } catch (error) {
      console.error('Error performing search:', error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Flex pt="3vh" direction="column" align="center">
      <Box w="100%" maxW="800px" px={4} position="relative">
        <Input
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyPress={(e) => {
            if (e.key === 'Enter') {
              setSearchQuery(inputValue);
              performSearch(inputValue);
            }
          }}
          placeholder="Search..."
          size="lg"
          borderColor="brand.600"
          _hover={{ borderColor: 'brand.700' }}
          _focus={{ borderColor: 'brand.700', boxShadow: '0 0 0 1px var(--chakra-colors-brand-700)' }}
        />
        {isLoading && (
          <Box position="absolute" right="24px" top="50%" transform="translateY(-50%)">
            <Spinner color="brand.600" />
          </Box>
        )}
      </Box>
      {results.length > 0 && (
        <VStack spacing={4} w="100%" maxW="800px" mt={8} px={4}>
          {results.map((result) => (
            <Card key={result.id} w="100%" variant="outline">
              <CardBody>
                <VStack align="stretch" spacing={3}>
                  <Link href={result.url} isExternal color="blue.600" fontWeight="bold">
                    {result.name}
                  </Link>
                  <Text fontSize="sm" color="gray.600">
                    {result.author} • {result.url} • {new Date(result.date).toLocaleDateString()}
                  </Text>
                  <Text>{result.summary}</Text>
                  <HStack spacing={2}>
                    {result.topics.split(",").map((topic, index) => (
                      <Tag key={index} size="sm" colorScheme="blue">
                        {topic}
                      </Tag>
                    ))}
                  </HStack>
                </VStack>
              </CardBody>
            </Card>
          ))}
        </VStack>
      )}
    </Flex>
  );
}

const App: React.FC = () => {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Search />} />
        <Route path="/links" element={<Links />} />
      </Routes>
    </Router>
  );
};

export default App;
