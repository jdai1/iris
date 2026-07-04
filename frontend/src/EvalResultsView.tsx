import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import {
  Badge,
  Box,
  Button,
  Flex,
  Heading,
  Stack,
  Text,
} from '@chakra-ui/react';
import { ArrowUpRight, Search } from 'lucide-react';
import { getLatestEvalReport } from './api';
import type { EvalReport, EvalResult, EvalResultDocument } from './types';

const verdictOrder = ['all', 'strong', 'partial', 'weak', 'no_results'];
const verdictLabels: Record<string, string> = {
  all: 'All verdicts',
  strong: 'Strong',
  partial: 'Partial',
  weak: 'Weak',
  no_results: 'No results',
};
const verdictColors: Record<string, { bg: string; color: string; border: string }> = {
  strong: { bg: '#edf7f0', color: '#1f6b3a', border: '#cde8d4' },
  partial: { bg: '#f8f4e8', color: '#806316', border: '#eadcae' },
  weak: { bg: '#f9eceb', color: '#9b332a', border: '#efcbc7' },
  no_results: { bg: '#f1f1f1', color: '#555', border: '#dedede' },
};

export function EvalResultsView() {
  const [report, setReport] = useState<EvalReport | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [domain, setDomain] = useState('all');
  const [verdict, setVerdict] = useState('all');
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<'question' | 'domain' | 'weakest'>('question');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void refresh();
  }, []);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const nextReport = await getLatestEvalReport();
      setReport(nextReport);
      setSelectedId((current) => current ?? nextReport.results[0]?.question.id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load eval report');
    } finally {
      setLoading(false);
    }
  }

  const results = report?.results ?? [];
  const domains = useMemo(() => Array.from(new Set(results.map((result) => result.question.domain))).sort(), [results]);
  const filteredResults = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const rows = results.filter((result) => {
      if (domain !== 'all' && result.question.domain !== domain) return false;
      if (verdict !== 'all' && result.verdict !== verdict) return false;
      if (!needle) return true;
      return [
        result.question.id,
        result.question.query,
        result.question.intent ?? '',
        result.question.domain,
        ...result.question.tags,
        ...result.results.flatMap((document) => [document.title, document.source, document.reason]),
      ]
        .join(' ')
        .toLowerCase()
        .includes(needle);
    });
    return rows.sort((left, right) => {
      if (sort === 'domain') return left.question.domain.localeCompare(right.question.domain) || left.question.id.localeCompare(right.question.id);
      if (sort === 'weakest') return weaknessScore(right) - weaknessScore(left);
      return left.question.id.localeCompare(right.question.id);
    });
  }, [domain, query, results, sort, verdict]);
  const selected = filteredResults.find((result) => result.question.id === selectedId) ?? filteredResults[0] ?? null;

  useEffect(() => {
    if (!selected && filteredResults[0]) {
      setSelectedId(filteredResults[0].question.id);
    }
  }, [filteredResults.length, selected?.question.id]);

  return (
    <Box as="section">
      <Flex className="eval-dev-header">
        <Box>
          <Text fontSize="11px" color="iris.500" fontWeight="700" textTransform="uppercase">Engineering eval viewer</Text>
          <Heading as="h2" mt="1" fontSize="2xl" fontWeight="650">Question Returns</Heading>
          <Text mt="1" color="iris.500" fontSize="13px">Spot-check each question against the article headlines and relevance text being returned.</Text>
        </Box>
        <Button type="button" onClick={refresh} variant="outline" borderRadius="0" loading={loading}>
          Refresh
        </Button>
      </Flex>

      {error && <div className="error">{error}</div>}
      {loading && !report && <div className="empty-state">Loading eval report...</div>}

      {report && (
        <Stack gap="3">
          <Flex className="eval-toolbar" gap="2" wrap="wrap" align="end">
            <Flex className="eval-search-control" align="center" gap="2">
              <Search size={14} color="#767676" />
              <input
                className="eval-filter-input"
                value={query}
                onChange={(event) => setQuery(event.currentTarget.value)}
                placeholder="Filter questions, returned articles, sources, reasons..."
              />
            </Flex>
            <FilterSelect value={domain} onChange={setDomain} label="Domain">
              <option value="all">All domains</option>
              {domains.map((item) => <option key={item} value={item}>{item}</option>)}
            </FilterSelect>
            <FilterSelect value={verdict} onChange={setVerdict} label="Verdict">
              {verdictOrder.map((item) => <option key={item} value={item}>{verdictLabels[item]}</option>)}
            </FilterSelect>
            <FilterSelect value={sort} onChange={(value) => setSort(value as typeof sort)} label="Sort">
              <option value="question">Question order</option>
              <option value="domain">Domain</option>
              <option value="weakest">Weakest first</option>
            </FilterSelect>
            <Box ml="auto" pb="1">
              <Text fontSize="12px" color="iris.500">
                {filteredResults.length} / {results.length} questions
              </Text>
            </Box>
          </Flex>
          <Box className="eval-verdict-note">
            <Text fontSize="12px" color="iris.700" lineHeight="1.45">
              <strong>Strong / Partial / Weak</strong> are heuristic labels from the eval runner. Strong means the top results look textually aligned with the question, Partial means plausible but worth checking, and Weak means the returned evidence looks thin. Treat them as triage hints, not truth.
            </Text>
          </Box>

          <Box className="eval-spotcheck-grid">
            <Box className="eval-question-list">
              {filteredResults.map((result) => (
                <QuestionReturnRow
                  key={result.question.id}
                  result={result}
                  active={selected?.question.id === result.question.id}
                  onSelect={() => setSelectedId(result.question.id)}
                />
              ))}
              {filteredResults.length === 0 && <div className="empty-state">No rows match these filters.</div>}
            </Box>
            <Box className="eval-detail-panel">
              {selected ? <EvalDetail result={selected} /> : <div className="empty-state">Select a question.</div>}
            </Box>
          </Box>
        </Stack>
      )}
    </Box>
  );
}

function FilterSelect({
  value,
  onChange,
  label,
  children,
}: {
  value: string;
  onChange: (value: string) => void;
  label: string;
  children: ReactNode;
}) {
  return (
    <Box as="label" display="grid" gap="1" minW="150px">
      <Text as="span" fontSize="10px" color="iris.500" fontWeight="650" textTransform="uppercase">{label}</Text>
      <select
        className="eval-filter-select"
        value={value}
        onChange={(event) => onChange(event.currentTarget.value)}
      >
        {children}
      </select>
    </Box>
  );
}

function QuestionReturnRow({
  result,
  active,
  onSelect,
}: {
  result: EvalResult;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <div className={active ? 'eval-return-row eval-row-active' : 'eval-return-row'} role="button" tabIndex={0} onClick={onSelect} onKeyDown={(event) => {
      if (event.key === 'Enter' || event.key === ' ') onSelect();
    }}>
      <Flex gap="2" align="center" minW="0">
        <Text className="eval-row-id">{result.question.id}</Text>
        <Text className="eval-row-domain">{result.question.domain}</Text>
        <Text className="eval-row-question">{result.question.query}</Text>
        <VerdictBadge verdict={result.verdict} />
      </Flex>
    </div>
  );
}

function EvalDetail({ result }: { result: EvalResult }) {
  return (
    <Stack gap="3" p="4">
      <Box className="eval-inspector-header">
        <Flex justify="space-between" gap="3" align="start">
          <Box minW="0">
            <Text fontSize="11px" color="iris.500" fontWeight="700">{result.question.id} · {result.question.domain}</Text>
            <Heading as="h3" mt="1" fontSize="17px" lineHeight="1.3" fontWeight="650">{result.question.query}</Heading>
          </Box>
          <VerdictBadge verdict={result.verdict} />
        </Flex>
        {result.question.intent ? (
          <Text mt="2" fontSize="12px" color="iris.500" lineHeight="1.4">{result.question.intent}</Text>
        ) : null}
        <Flex mt="2" gap="1.5" wrap="wrap">
          {result.question.tags.map((tag) => (
            <Badge key={tag} borderRadius="0" bg="#f7f7f5" color="iris.700" border="1px solid #ececea">{tag}</Badge>
          ))}
        </Flex>
      </Box>

      <Box>
        <Text fontSize="11px" fontWeight="700" color="iris.500" mb="2" textTransform="uppercase">Returned articles</Text>
        <Stack gap="0">
          {result.results.map((document, index) => (
            <Box key={`${document.document_id}-${index}`} className="eval-return-card">
              <Flex gap="2.5" align="start">
                <Text as="span" className="eval-card-rank">{index + 1}</Text>
                <Box minW="0" flex="1">
                  <Flex justify="space-between" gap="3" align="start">
                    <Box minW="0">
                      <a className="eval-card-title-link" href={document.url}>{document.title}</a>
                      <Text fontSize="11px" color="iris.500">{document.source}</Text>
                    </Box>
                    <a className="eval-result-link" href={document.url} aria-label="Open result">
                      <ArrowUpRight size={15} />
                    </a>
                  </Flex>
                  <Text mt="1" className="eval-card-reason">{document.reason}</Text>
                  {document.summary && <Text mt="1" className="eval-card-summary">{document.summary}</Text>}
                </Box>
              </Flex>
            </Box>
          ))}
        </Stack>
      </Box>

      <Box>
        <Text fontSize="11px" fontWeight="700" color="iris.500" mb="2" textTransform="uppercase">Answer synthesis</Text>
        <Box border="1px solid #ededed" bg="#fbfbfa" p="2.5">
          <Text whiteSpace="pre-wrap" fontSize="12px" lineHeight="1.55" color="iris.700">{result.answer || 'No answer synthesized.'}</Text>
        </Box>
      </Box>
    </Stack>
  );
}

function VerdictBadge({ verdict }: { verdict: string }) {
  const colors = verdictColors[verdict] ?? verdictColors.partial;
  return (
    <Badge borderRadius="0" bg={colors.bg} color={colors.color} border={`1px solid ${colors.border}`} fontSize="10px" fontWeight="700">
      {verdictLabels[verdict] ?? verdict}
    </Badge>
  );
}

function weaknessScore(result: EvalResult): number {
  const verdictWeight = result.verdict === 'no_results' ? 4 : result.verdict === 'weak' ? 3 : result.verdict === 'partial' ? 1 : 0;
  return verdictWeight + (1 - result.metrics.query_term_coverage) + (1 - result.metrics.top_result_coverage);
}
