// Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.
//
// Example Flyto2 module pack written in Node.js.
//
//   node index.js --manifest   prints the flyto.pack.v1 manifest
//   node index.js              serves the modules over JSON-RPC on stdio
//
// The same two modules written in Python with @register_module produce the
// same manifest rows -- see tests/core/pack/test_node_example_pack.py.
'use strict';

const { definePack, registerModule, main } = require('./flyto');

definePack({
  id: 'com.example.greeter',
  version: '0.1.0',
  namespaces: ['greeter'],
  description: 'Example pack written in Node.js: greetings and repetition.',
  min_host: '2.37.0',
});

registerModule({
  module_id: 'greeter.greet',
  version: '1.0.0',
  category: 'greeter',
  label: 'Greet',
  description: 'Return a greeting for a name',
  icon: 'Hand',
  tags: ['example', 'greeting'],
  params_schema: {
    name: {
      type: 'string',
      label: 'Name',
      description: 'Who to greet',
      placeholder: 'Ada',
      required: true,
      maxLength: 64,
    },
  },
  output_schema: {
    greeting: { type: 'string', description: 'The greeting' },
  },
  provides_capability: 'greeter.greet',
  contract: {
    actuates: false,
    safety_class: 'read_only',
    requires_safe_stop: false,
    cancellable: true,
    idempotent: true,
  },
  timeout_ms: 5000,
  handler: async ({ name }) => ({ greeting: `Hello, ${name}!` }),
});

registerModule({
  module_id: 'greeter.repeat',
  version: '1.0.0',
  category: 'greeter',
  label: 'Repeat',
  description: 'Repeat a text a bounded number of times',
  icon: 'Repeat',
  tags: ['example'],
  params_schema: {
    text: {
      type: 'string',
      label: 'Text',
      description: 'Text to repeat',
      placeholder: 'hi',
      required: true,
    },
    times: {
      type: 'integer',
      label: 'Times',
      description: 'How many times',
      default: 2,
      min: 1,
      max: 5,
    },
  },
  output_schema: {
    text: { type: 'string', description: 'The repeated text' },
  },
  timeout_ms: 5000,
  handler: async ({ text, times = 2 }) => {
    if (!text.trim()) {
      const error = new Error('text is blank');
      error.code = 'BLANK_TEXT';
      throw error;
    }
    return { text: Array(times).fill(text).join(' ') };
  },
});

main();
