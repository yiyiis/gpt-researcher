import React, { ChangeEvent } from 'react';

interface LayoutSelectorProps {
  layoutType: string;
  onLayoutChange: (event: ChangeEvent<HTMLSelectElement>) => void;
}

export default function LayoutSelector({ layoutType, onLayoutChange }: LayoutSelectorProps) {
  return (
    <div className="form-group">
      <label htmlFor="layoutType" className="agent_question">布局类型 </label>
      <select
        name="layoutType"
        id="layoutType"
        value={layoutType}
        onChange={onLayoutChange}
        className="form-control-static"
        required
      >
        <option value="research">研究模式 - 传统研究布局，展示详细结果</option>
        <option value="copilot">副驾驶模式 - 并排显示研究和聊天界面</option>
      </select>
    </div>
  );
} 