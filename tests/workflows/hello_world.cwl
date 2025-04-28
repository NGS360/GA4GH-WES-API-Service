cwlVersion: v1.0
class: Workflow
inputs: []
outputs:
  output_file:
    type: File
    outputSource: say_hello/output_file

steps:
  say_hello:
    run:
      class: CommandLineTool
      baseCommand: [echo, "Hello, World!"]
      stdout: hello.txt
      inputs: []
      outputs:
        output_file:
          type: stdout
    in: []
    out: [output_file]

requirements:
  DockerRequirement:
    dockerPull: ubuntu:latest