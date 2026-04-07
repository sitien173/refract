import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';

/**
 * Extract YAML frontmatter from a skill file.
 *
 * @param {string} filePath
 * @returns {{name: string, description: string}}
 */
function extractFrontmatter(filePath) {
    try {
        const content = fs.readFileSync(filePath, 'utf8');
        const lines = content.split('\n');

        let inFrontmatter = false;
        let name = '';
        let description = '';

        for (const line of lines) {
            const normalizedLine = line.trim();

            if (normalizedLine === '---') {
                if (inFrontmatter) break;
                inFrontmatter = true;
                continue;
            }

            if (!inFrontmatter) continue;

            const match = normalizedLine.match(/^(\w+):\s*(.*)$/);
            if (!match) continue;

            const [, key, value] = match;
            if (key === 'name') name = value.trim();
            if (key === 'description') description = value.trim();
        }

        return { name, description };
    } catch {
        return { name: '', description: '' };
    }
}

/**
 * Find all SKILL.md files in a directory recursively.
 *
 * @param {string} dir
 * @param {string} sourceType
 * @param {number} maxDepth
 * @returns {Array<{path: string, skillFile: string, name: string, description: string, sourceType: string}>}
 */
function findSkillsInDir(dir, sourceType, maxDepth = 3) {
    const skills = [];

    if (!fs.existsSync(dir)) return skills;

    function recurse(currentDir, depth) {
        if (depth > maxDepth) return;

        const entries = fs.readdirSync(currentDir, { withFileTypes: true });

        for (const entry of entries) {
            if (!entry.isDirectory()) continue;

            const fullPath = path.join(currentDir, entry.name);
            const skillFile = path.join(fullPath, 'SKILL.md');

            if (fs.existsSync(skillFile)) {
                const { name, description } = extractFrontmatter(skillFile);
                skills.push({
                    path: fullPath,
                    skillFile,
                    name: name || entry.name,
                    description: description || '',
                    sourceType
                });
            }

            recurse(fullPath, depth + 1);
        }
    }

    recurse(dir, 0);
    return skills;
}

/**
 * Resolve a skill name to its file path.
 *
 * @param {string} skillName
 * @param {string} superpowersDir
 * @param {string} personalDir
 * @returns {{skillFile: string, sourceType: string, skillPath: string} | null}
 */
function resolveSkillPath(skillName, superpowersDir, personalDir) {
    const forceSuperpowers = skillName.startsWith('superpowers:');
    const actualSkillName = forceSuperpowers ? skillName.replace(/^superpowers:/, '') : skillName;

    if (!forceSuperpowers && personalDir) {
        const personalSkillFile = path.join(personalDir, actualSkillName, 'SKILL.md');
        if (fs.existsSync(personalSkillFile)) {
            return {
                skillFile: personalSkillFile,
                sourceType: 'personal',
                skillPath: actualSkillName
            };
        }
    }

    if (superpowersDir) {
        const superpowersSkillFile = path.join(superpowersDir, actualSkillName, 'SKILL.md');
        if (fs.existsSync(superpowersSkillFile)) {
            return {
                skillFile: superpowersSkillFile,
                sourceType: 'superpowers',
                skillPath: actualSkillName
            };
        }
    }

    return null;
}

/**
 * Check whether a git repo has upstream updates available.
 *
 * @param {string} repoDir
 * @returns {boolean}
 */
function checkForUpdates(repoDir) {
    try {
        const output = execSync('git fetch origin && git status --porcelain=v1 --branch', {
            cwd: repoDir,
            timeout: 3000,
            encoding: 'utf8',
            stdio: 'pipe'
        });

        return output
            .split('\n')
            .some((line) => line.startsWith('## ') && line.includes('[behind '));
    } catch {
        return false;
    }
}

/**
 * Strip YAML frontmatter from markdown content.
 *
 * @param {string} content
 * @returns {string}
 */
function stripFrontmatter(content) {
    const lines = content.split('\n');
    let inFrontmatter = false;
    let frontmatterEnded = false;
    const contentLines = [];

    for (const line of lines) {
        if (line.trim() === '---') {
            if (inFrontmatter) {
                frontmatterEnded = true;
                continue;
            }
            inFrontmatter = true;
            continue;
        }

        if (frontmatterEnded || !inFrontmatter) {
            contentLines.push(line);
        }
    }

    return contentLines.join('\n').trim();
}

export {
    checkForUpdates,
    extractFrontmatter,
    findSkillsInDir,
    resolveSkillPath,
    stripFrontmatter
};
