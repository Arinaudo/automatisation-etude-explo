@echo off
REM Agent du poste Amont : execute les robots lances depuis le site. Laisser cette fenetre ouverte (reduite).
cd /d "%~dp0"
title Agent Amont
python 2026_10_28_amont_agent_poste.py %*
pause
