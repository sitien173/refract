/**
 * Superpowers-CCG plugin for OpenCode.ai.
 *
 * Exposes `use_skill` and `find_skills`, and injects the repo workflow guide
 * so OpenCode sessions inherit the same checkpoint-driven workflow.
 */

import fs from 'fs';
import os from 'os';
import path from 'path';
import { fileURLToPath } from 'url';
import { tool } from '@opencode-ai/plugin/tool';
import * as skillsCore from '../../lib/skills-core.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const superpowersRoot = path.resolve(__dirname, '../..');
const workflowGuidePath = path.join(superpowersRoot, 'superpowers-ccg.md');
const readmePath = path.join(superpowersRoot, 'README.md');

function readFileIfExists(filePath) {
  if (!fs.existsSync(filePath)) return null;
  return fs.readFileSync(filePath, 'utf8');
}

function getWorkflowBootstrap(compact = false) {
  const workflowGuide = readFileIfExists(workflowGuidePath);
  const readme = readFileIfExists(readmePath);

  if (compact) {
    return `<EXTREMELY_IMPORTANT>
You are operating with Superpowers-CCG workflow rules in OpenCode.

- Treat Claude/OpenCode as the orchestrator.
- Use \`use_skill\` to load repo skills before starting non-trivial work.
- Follow CP0 -> CP1 -> CP2 -> CP3 -> CP4.
- Backend, scripts, CI/CD, Docker, infra -> Codex.
- Frontend UI/components/styles -> Gemini.
- Finish with a CP4 spec review against the original request and success criteria.

Tool mapping:
- \`TodoWrite\` -> \`update_plan\`
- Claude \`Task\` subagents -> OpenCode @mentions
- \`Skill\` tool -> \`use_skill\`
</EXTREMELY_IMPORTANT>`;
  }

  const sections = [];

  if (workflowGuide) {
    sections.push(`Current workflow reference:\n\n${workflowGuide}`);
  }

  if (readme) {
    sections.push(`Repository overview:\n\n${readme}`);
  }

  if (sections.length === 0) return null;

  return `<EXTREMELY_IMPORTANT>
You have Superpowers-CCG workflow support loaded for this repository.

Follow the workflow and skill guidance below. Do not call \`use_skill\` for a generic bootstrap skill first; use it for the specific task skill you need.

Tool mapping for OpenCode:
- \`TodoWrite\` -> \`update_plan\`
- Claude \`Task\` subagents -> OpenCode @mentions
- \`Skill\` tool -> \`use_skill\`
- Native read/write/edit/shell tools remain unchanged

${sections.join('\n\n---\n\n')}
</EXTREMELY_IMPORTANT>`;
}

function getVisibleStartupMessage() {
  return `Superpowers-CCG is loaded for this session.

Available custom tools:
- find_skills
- use_skill

Examples:
- "Call the find_skills tool and show the raw output."
- "Call the use_skill tool with skill_name \\"superpowers:brainstorming\\"."

Note: this plugin adds tools and workflow bootstrap guidance. It does not add Claude-style slash commands.`;
}

export const SuperpowersPlugin = async ({ client, directory }) => {
  const homeDir = os.homedir();
  const projectDir = directory || process.cwd();
  const projectSkillsDir = path.join(projectDir, '.opencode', 'skills');
  const superpowersSkillsDir = path.join(superpowersRoot, 'skills');
  const personalSkillsDir = path.join(homeDir, '.config', 'opencode', 'skills');

  const injectBootstrap = async (sessionID, compact = false) => {
    const bootstrap = getWorkflowBootstrap(compact);
    if (!bootstrap) return false;

    try {
      await client.session.prompt({
        path: { id: sessionID },
        body: {
          noReply: true,
          parts: [{ type: 'text', text: bootstrap, synthetic: true }]
        }
      });
      return true;
    } catch {
      return false;
    }
  };

  const injectVisibleStartupMessage = async (sessionID) => {
    try {
      await client.session.prompt({
        path: { id: sessionID },
        body: {
          noReply: true,
          parts: [{ type: 'text', text: getVisibleStartupMessage() }]
        }
      });
      return true;
    } catch {
      return false;
    }
  };

  return {
    tool: {
      use_skill: tool({
        description: 'Load and read a specific skill to guide your work.',
        args: {
          skill_name: tool.schema
            .string()
            .describe('Skill name, e.g. "superpowers:brainstorming", "project:my-skill", or "my-skill"')
        },
        execute: async ({ skill_name }, context) => {
          const forceProject = skill_name.startsWith('project:');
          const actualSkillName = forceProject ? skill_name.replace(/^project:/, '') : skill_name;

          let resolved = null;

          if (forceProject || !skill_name.startsWith('superpowers:')) {
            const projectSkillFile = path.join(projectSkillsDir, actualSkillName, 'SKILL.md');
            if (fs.existsSync(projectSkillFile)) {
              resolved = {
                skillFile: projectSkillFile,
                sourceType: 'project',
                skillPath: actualSkillName
              };
            }
          }

          if (!resolved && !forceProject) {
            resolved = skillsCore.resolveSkillPath(skill_name, superpowersSkillsDir, personalSkillsDir);
          }

          if (!resolved) {
            return `Error: Skill "${skill_name}" not found.\n\nRun find_skills to inspect available skills.`;
          }

          const fullContent = fs.readFileSync(resolved.skillFile, 'utf8');
          const { name, description } = skillsCore.extractFrontmatter(resolved.skillFile);
          const content = skillsCore.stripFrontmatter(fullContent);
          const skillDirectory = path.dirname(resolved.skillFile);
          const skillLabel = name || skill_name;
          const header = `# ${skillLabel}
# ${description || ''}
# Supporting files live in ${skillDirectory}
# ============================================`;

          try {
            await client.session.prompt({
              path: { id: context.sessionID },
              body: {
                noReply: true,
                parts: [
                  { type: 'text', text: `Loading skill: ${skillLabel}`, synthetic: true },
                  { type: 'text', text: `${header}\n\n${content}`, synthetic: true }
                ]
              }
            });
          } catch {
            return `${header}\n\n${content}`;
          }

          return `Launching skill: ${skillLabel}`;
        }
      }),
      find_skills: tool({
        description: 'List all available project, personal, and superpowers skills.',
        args: {},
        execute: async () => {
          const projectSkills = skillsCore.findSkillsInDir(projectSkillsDir, 'project', 3);
          const personalSkills = skillsCore.findSkillsInDir(personalSkillsDir, 'personal', 3);
          const superpowersSkills = skillsCore.findSkillsInDir(superpowersSkillsDir, 'superpowers', 3);
          const allSkills = [...projectSkills, ...personalSkills, ...superpowersSkills];

          if (allSkills.length === 0) {
            return 'No skills found. Install superpowers skills or add project-local skills under .opencode/skills/.';
          }

          let output = 'Available skills:\n\n';

          for (const skill of allSkills) {
            const namespace =
              skill.sourceType === 'project'
                ? 'project:'
                : skill.sourceType === 'personal'
                  ? ''
                  : 'superpowers:';

            const skillName = skill.name || path.basename(skill.path);
            output += `${namespace}${skillName}\n`;
            if (skill.description) output += `  ${skill.description}\n`;
            output += `  Directory: ${skill.path}\n\n`;
          }

          return output;
        }
      })
    },
    event: async ({ event }) => {
      const sessionID =
        event.properties?.info?.id ||
        event.properties?.sessionID ||
        event.session?.id;

      if (!sessionID) return;

      if (event.type === 'session.created') {
        await injectBootstrap(sessionID, false);
        await injectVisibleStartupMessage(sessionID);
      }

      if (event.type === 'session.compacted') {
        await injectBootstrap(sessionID, true);
      }
    }
  };
};
