import { Box, Select, Spinner, Text } from '@chakra-ui/react';
import React, { useState, useEffect } from 'react';

interface Link {
  id: number;
  url: string,
  external_domains: string,
  external_links: string,
}

const Links: React.FC = () => {
  const [links, setLinks] = useState<Link[]>([]);
  const [selectedLink, setSelectedLink] = useState<Link | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const handleLinkChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const linkId = event.target.value;
    if (!linkId) {
      setSelectedLink(null);
      return;
    }
    const link = links.find(u => u.id === Number(linkId));
    setSelectedLink(link || null);
  };

  useEffect(() => {
    const fetchUrls = async () => {
      try {
        const response = await fetch('http://127.0.0.1:5000/api/urls');
        if (!response.ok) {
          throw new Error('Failed to fetch urls');
        }
        const urls = await response.json();
        setLinks(urls);
      } catch (error) {
        console.error('Error fetching urls:', error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchUrls();
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
      <Select 
        placeholder="Select URL" 
        onChange={handleLinkChange}
        mb={4}
      >
        {links.map((link) => (
          <option key={link.id} value={link.id}>
            {link.url}
          </option>
        ))}
      </Select>

      {selectedLink && (
        <Box>
          <Text fontSize="lg" fontWeight="bold" mb={2}>External Domains:</Text>
          <Box mb={4}>
            {selectedLink.external_domains.split(",").map((domain, index) => (
              <Text key={index}>{domain}</Text>
            ))}
          </Box>

          <Text fontSize="lg" fontWeight="bold" mb={2}>External Links:</Text>
          <Box>
            {selectedLink.external_links.split(",").map((link, index) => (
              <Text key={index}>
                <a href={link} target="_blank" rel="noopener noreferrer" style={{ color: 'blue', textDecoration: 'underline' }}>
                  {link}
                </a>
              </Text>
            ))}
          </Box>
        </Box>
      )}
    </Box>
  );
};

export default Links;
