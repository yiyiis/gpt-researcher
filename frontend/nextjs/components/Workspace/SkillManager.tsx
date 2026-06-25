import React, { useState, useEffect, useCallback } from 'react';

interface InstructionSkill {
  name: string;
  description: string;
  dir: string;
  type: 'instruction';
}

interface ToolSkill {
  name: string;
  description: string;
  file: string;
}

const SkillManager: React.FC = () => {
  const [instructionSkills, setInstructionSkills] = useState<InstructionSkill[]>([]);
  const [toolSkills, setToolSkills] = useState<ToolSkill[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchSkills = useCallback(async () => {
    try {
      const res = await fetch('/api/skills');
      if (res.ok) {
        const data = await res.json();
        setInstructionSkills(data.instruction_skills || []);
        setToolSkills(data.tool_skills || []);
      }
    } catch (e) {
      console.error('加载 skills 失败', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);

  const deleteInstructionSkill = async (skill: InstructionSkill) => {
    if (!confirm(`确定删除指令型 skill「${skill.name}」吗？\n这会删除整个目录 ${skill.dir}/（含 SKILL.md 及附属文件）。`)) return;
    try {
      const res = await fetch(`/api/skills?name=${encodeURIComponent(skill.name)}&type=instruction`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setInstructionSkills((prev) => prev.filter((s) => s.name !== skill.name));
      } else {
        const err = await res.json().catch(() => ({}));
        alert(`删除失败: ${err.error || res.status}`);
      }
    } catch (e) {
      alert('删除失败，请查看控制台');
    }
  };

  const deleteToolSkill = async (skill: ToolSkill) => {
    if (!confirm(`确定删除工具型 skill「${skill.name}」吗？\n这会删除源文件 ${skill.file}。`)) return;
    try {
      const res = await fetch(`/api/skills?name=${encodeURIComponent(skill.name)}&type=tool`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setToolSkills((prev) => prev.filter((s) => s.name !== skill.name));
      } else {
        const err = await res.json().catch(() => ({}));
        alert(`删除失败: ${err.error || res.status}`);
      }
    } catch (e) {
      alert('删除失败，请查看控制台');
    }
  };

  if (loading) {
    return <p className="ws-skill-empty">正在加载...</p>;
  }

  return (
    <div className="ws-skill-container">
      <div className="ws-skill-hint">
        <i className="fas fa-info-circle" style={{ marginRight: 4 }} />
        指令型 skill 放 <code>skills/&lt;目录&gt;/SKILL.md</code>，工具型放 <code>custom_skills/*.py</code>
      </div>

      {/* 指令型 skill */}
      {instructionSkills.length > 0 && (
        <>
          <div className="ws-skill-section-title">
            <i className="fas fa-book-open" /> 指令型 Skill（{instructionSkills.length}）
            <small className="ws-skill-section-desc">研究时注入方法论指导</small>
          </div>
          <ul className="ws-skill-list">
            {instructionSkills.map((skill) => (
              <li key={skill.name} className="ws-skill-item instruction">
                <div className="ws-skill-info">
                  <div className="ws-skill-name">
                    <i className="fas fa-book ws-skill-icon" />
                    <span>{skill.name}</span>
                  </div>
                  {skill.description && (
                    <p className="ws-skill-desc" title={skill.description}>
                      {skill.description.slice(0, 90)}
                    </p>
                  )}
                  <span className="ws-skill-file">
                    <i className="far fa-folder" style={{ marginRight: 3 }} />
                    {skill.dir}/
                  </span>
                </div>
                <button
                  className="ws-skill-delete"
                  onClick={() => deleteInstructionSkill(skill)}
                  title="删除 skill 目录"
                >
                  <i className="fas fa-trash" />
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      {/* 工具型 skill */}
      {toolSkills.length > 0 && (
        <>
          <div className="ws-skill-section-title" style={{ marginTop: instructionSkills.length > 0 ? 16 : 0 }}>
            <i className="fas fa-bolt" /> 工具型 Skill（{toolSkills.length}）
            <small className="ws-skill-section-desc">研究时 LLM 可调用</small>
          </div>
          <ul className="ws-skill-list">
            {toolSkills.map((skill) => (
              <li key={skill.name} className="ws-skill-item tool">
                <div className="ws-skill-info">
                  <div className="ws-skill-name">
                    <i className="fas fa-bolt ws-skill-icon" />
                    <span>{skill.name}</span>
                  </div>
                  {skill.description && (
                    <p className="ws-skill-desc" title={skill.description}>
                      {skill.description.split('\n')[0].slice(0, 90)}
                    </p>
                  )}
                  <span className="ws-skill-file">
                    <i className="fab fa-python" style={{ marginRight: 3 }} />
                    {skill.file}
                  </span>
                </div>
                <button
                  className="ws-skill-delete"
                  onClick={() => deleteToolSkill(skill)}
                  title="删除 skill 文件"
                >
                  <i className="fas fa-trash" />
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      {/* 空状态 */}
      {instructionSkills.length === 0 && toolSkills.length === 0 && (
        <p className="ws-skill-empty">
          暂无 skill。
          <br />
          指令型：创建 <code>skills/&lt;name&gt;/SKILL.md</code>（带 name + description frontmatter）
          <br />
          工具型：创建 <code>custom_skills/&lt;name&gt;.py</code>（用 @tool 装饰函数）
        </p>
      )}
    </div>
  );
};

export default SkillManager;
