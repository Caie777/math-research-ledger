import z from '@deepseek-ai/schemastery';
import * as mcp from '@deepseek-ai/dsh-mcp-client';
import { transportConfig } from './transport.mjs';

export const name = 'math-research-ledger';
export const inject = mcp.inject;
export const Config = z.object({ python: z.string().default(''), workspace: z.string().default('') });

// The official bridge owns discovery, tools, subprocess disposal and reconnection.
export async function apply(ctx, config) {
  await mcp.apply(ctx, await transportConfig(config));
}
