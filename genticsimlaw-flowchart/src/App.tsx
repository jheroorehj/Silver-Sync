/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';
import { TransformWrapper, TransformComponent, ReactZoomPanPinchRef } from 'react-zoom-pan-pinch';
import { ZoomIn, ZoomOut, Maximize } from 'lucide-react';

mermaid.initialize({
  startOnLoad: false,
  theme: 'default',
  themeVariables: {
    clusterBkg: '#FFF9C4',
    clusterBorder: '#FBC02D',
  },
  securityLevel: 'loose',
  fontFamily: 'Inter, sans-serif',
});

const chartCode = `flowchart TD
    classDef rule fill:#E1F5FE,stroke:#0288D1,stroke-width:2px,stroke-dasharray: 5 5,color:#000
    classDef gemma fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px,color:#000
    classDef aws fill:#FFF3E0,stroke:#FF9900,stroke-width:2px,color:#000
    classDef debate fill:#FFF9C4,stroke:#FBC02D,stroke-width:2px,color:#000
    classDef endpoint fill:#F3E5F5,stroke:#8E24AA,stroke-width:2px,color:#000

    Start(["재진 트리거"]) --> Gate

    subgraph Stage1 ["Stage 1. Gate Agent"]
        Gate(("<div style='width:160px;height:54px;display:flex;align-items:center;justify-content:center;text-align:center;'>Gate Agent<br/>Gemma 4 26B A4B</div>")):::gemma
        Tool_Stats[["Tool: 통계 연산기"]]:::rule

        Gate -->|"Input: 타임스탬프, 설문 원본"| Tool_Stats
        Tool_Stats -->|"Output: 분산값, 이상치 Flag"| Gate
    end

    Gate -->|"전처리된 신뢰도 JSON"| Reasoner

    subgraph Stage2 ["Stage 2. Reasoner & AgenticSimLaw"]
        Reasoner(("<div style='width:160px;height:54px;display:flex;align-items:center;justify-content:center;text-align:center;'>Reasoner Agent<br/>Gemma 4 26B A4B</div>")):::gemma
        Tool_DUR[["Tool: DUR / 수열"]]:::rule

        Reasoner -->|"Input: 신규처방+기존처방"| Tool_DUR
        Tool_DUR -->|"Output: NSAIDs-ACE 상호작용 매칭"| Reasoner

        Reasoner -->|"추출된 쟁점 1~3개 전달"| Debate_Room

        subgraph Debate_Room ["재진 법정 공방"]
            Pros(("<div style='width:160px;height:54px;display:flex;align-items:center;justify-content:center;text-align:center;'>검사 Agent<br/>Gemma 4 31B</div>")):::gemma
            Def(("<div style='width:160px;height:54px;display:flex;align-items:center;justify-content:center;text-align:center;'>변호사 Agent<br/>Gemma 4 31B</div>")):::gemma
            Tool_RAG[["Tool: 진료지침(고혈압/당뇨) RAG"]]:::rule

            Pros -->|"Input: 쟁점 키워드"| Tool_RAG
            Def -->|"Input: 쟁점 키워드"| Tool_RAG
            Tool_RAG -->|"Output: 가이드라인 원문 청크"| Pros & Def
            Pros <-->|"다중 턴 공방"| Def
        end
    end

    Debate_Room -->|"토론 로그 및 논거"| Judge

    subgraph Stage3 ["Stage 3. Judge Agent"]
        Judge(("<div style='width:160px;height:54px;display:flex;align-items:center;justify-content:center;text-align:center;'>Judge Agent<br/>AWS Kiro API</div>")):::aws
        Tool_RedFlag[["Tool: 하드게이트"]]:::rule

        Judge -->|"Input: 환자 프로파일 요약"| Tool_RedFlag
        Tool_RedFlag -->|"Output: Red Flag 여부 (T/F)"| Judge
    end

    Judge -->|"대면/비대면 최종 라벨 + 결론/근거"| Orch

    subgraph Stage4 ["Stage 4. Orchestrator Agent"]
        Orch(("<div style='width:160px;height:54px;display:flex;align-items:center;justify-content:center;text-align:center;'>Orchestrator Agent<br/>Gemma 4 26B A4B</div>")):::gemma
        Tool_Action[["Tool: GIS, 건강보험공단 전자처방전 API"]]:::rule

        Orch -->|"Input: 환자 위치, 조제 약물"| Tool_Action
        Tool_Action -->|"Output: 1순위 약국 매칭, 재고 상태"| Orch
        Orch -->|"최종 발송"| Out(["매칭 약국, 결론과 판단 근거 JSON"]):::endpoint
    end`;

export default function App() {
  const [svg, setSvg] = useState<{ html: string; width: number } | null>(null);
  const transformRef = useRef<ReactZoomPanPinchRef>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const renderChart = async () => {
      try {
        const id = 'mermaid-chart-' + Math.random().toString(36).substr(2, 9);
        const { svg } = await mermaid.render(id, chartCode);

        // Post-process SVG to left-align subgraph labels
        const parser = new DOMParser();
        const doc = parser.parseFromString(svg, 'image/svg+xml');

        const clusters = doc.querySelectorAll('.cluster');
        clusters.forEach(cluster => {
          const rect = cluster.querySelector('rect');
          const labelGroup = cluster.querySelector('.cluster-label');

          if (rect && labelGroup) {
            const rectX = parseFloat(rect.getAttribute('x') || '0');
            const rectWidth = parseFloat(rect.getAttribute('width') || '0');

            let labelX = 0;
            const transform = labelGroup.getAttribute('transform');
            if (transform) {
              const match = transform.match(/translate\(([^,)]+)/);
              if (match) labelX = parseFloat(match[1]);
            }

            const padding = 16;
            const targetX = rectX - labelX + padding;

            const foreignObject = labelGroup.querySelector('foreignObject');
            const text = labelGroup.querySelector('text');

            if (foreignObject) {
              foreignObject.setAttribute('x', targetX.toString());
              foreignObject.setAttribute('width', (rectWidth - padding * 2).toString());
              const div = foreignObject.querySelector('div');
              if (div) {
                div.style.display = 'flex';
                div.style.justifyContent = 'flex-start';
                div.style.textAlign = 'left';
                div.style.width = '100%';
              }
            } else if (text) {
              text.setAttribute('x', targetX.toString());
              text.setAttribute('text-anchor', 'start');
              const tspans = text.querySelectorAll('tspan');
              tspans.forEach(tspan => {
                tspan.setAttribute('x', targetX.toString());
                tspan.setAttribute('text-anchor', 'start');
              });
            }
          }
        });

        const svgElement = doc.querySelector('svg');
        let finalSvgWidth = 800;
        if (svgElement) {
          // Use viewBox to get real pixel dimensions (mermaid outputs width="100%")
          const viewBox = svgElement.getAttribute('viewBox');
          if (viewBox) {
            const parts = viewBox.split(' ');
            if (parts.length >= 4) {
              finalSvgWidth = parseFloat(parts[2]);
              const vbHeight = parseFloat(parts[3]);
              svgElement.setAttribute('width', finalSvgWidth + 'px');
              svgElement.setAttribute('height', vbHeight + 'px');
            }
          }
          svgElement.style.maxWidth = 'none';

          // Move edgePaths and edgeLabels to the end of their parent to render them on top
          const edgePaths = svgElement.querySelector('.edgePaths');
          const edgeLabels = svgElement.querySelector('.edgeLabels');
          if (edgePaths && edgePaths.parentNode) {
            edgePaths.parentNode.appendChild(edgePaths);
          }
          if (edgeLabels && edgeLabels.parentNode) {
            edgeLabels.parentNode.appendChild(edgeLabels);
          }
        }

        setSvg({ html: doc.documentElement.outerHTML, width: finalSvgWidth });
      } catch (error) {
        console.error('Failed to render mermaid chart', error);
      }
    };
    renderChart();
  }, []);

  // Fit to width once SVG is rendered
  useEffect(() => {
    if (!svg || !transformRef.current || !containerRef.current) return;
    requestAnimationFrame(() => {
      const container = containerRef.current;
      if (!container || !transformRef.current) return;
      const padding = 32;
      const scale = (container.clientWidth - padding * 2) / svg.width;
      transformRef.current.setTransform(padding, padding, scale);
    });
  }, [svg]);

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col font-sans text-gray-900">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between sticky top-0 z-10">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-gray-900">AgenticSimLaw Architecture</h1>
          <p className="text-sm text-gray-500 mt-1">Courtroom Debate Flowchart</p>
        </div>
      </header>

      <main className="flex-1 flex overflow-hidden">
        <div ref={containerRef} className="flex-1 relative bg-white m-6 rounded-xl shadow-sm border border-gray-200 overflow-hidden flex flex-col">
          <TransformWrapper
            ref={transformRef}
            initialScale={1}
            minScale={0.05}
            maxScale={20}
            limitToBounds={false}
            centerZoomedOut={false}
            wheel={{ step: 0.15 }}
            doubleClick={{ step: 1 }}
          >
            {({ zoomIn, zoomOut }) => (
              <>
                <div className="absolute top-4 right-4 z-10 flex flex-col space-y-2 bg-white rounded-lg shadow-md border border-gray-200 p-1">
                  <button
                    onClick={() => zoomIn()}
                    className="p-2 hover:bg-gray-100 rounded-md transition-colors text-gray-600"
                    title="Zoom In"
                  >
                    <ZoomIn className="w-5 h-5" />
                  </button>
                  <button
                    onClick={() => zoomOut()}
                    className="p-2 hover:bg-gray-100 rounded-md transition-colors text-gray-600"
                    title="Zoom Out"
                  >
                    <ZoomOut className="w-5 h-5" />
                  </button>
                  <div className="h-px bg-gray-200 mx-1 my-1" />
                  <button
                    onClick={() => {
                      if (!containerRef.current || !transformRef.current || !svg) return;
                      const padding = 32;
                      const scale = (containerRef.current.clientWidth - padding * 2) / svg.width;
                      transformRef.current.setTransform(padding, padding, scale);
                    }}
                    className="p-2 hover:bg-gray-100 rounded-md transition-colors text-gray-600"
                    title="Fit to Width"
                  >
                    <Maximize className="w-5 h-5" />
                  </button>
                </div>
                <TransformComponent wrapperClass="!w-full !h-full" contentClass="">
                  {svg ? (
                    <div dangerouslySetInnerHTML={{ __html: svg.html }} />
                  ) : (
                    <div className="flex items-center justify-center h-full text-gray-400">
                      Rendering diagram...
                    </div>
                  )}
                </TransformComponent>
              </>
            )}
          </TransformWrapper>
        </div>
      </main>
    </div>
  );
}
