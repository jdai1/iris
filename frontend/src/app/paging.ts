import type { Page } from '../types';

export const emptyPage = <T,>(): Page<T> => ({
  items: [],
  total: 0,
  limit: 50,
  offset: 0,
  has_next: false,
  has_previous: false,
});
