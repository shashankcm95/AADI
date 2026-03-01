/**
 * Configure @testing-library/react-native defaults.
 *
 * React 19 batches state updates from resolved promises differently,
 * so the default 1 000 ms asyncUtilTimeout is not always sufficient
 * for waitFor / findBy* queries to observe the first post-loading render.
 */
const { configure } = require('@testing-library/react-native');

configure({ asyncUtilTimeout: 5000 });
