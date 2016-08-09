'''
Created on Aug 2, 2016

@author: ming.li
'''
from __future__ import unicode_literals
import sys
import re
import xml.etree.ElementTree as ET
# from diff_cover.git_diff import GitDiffTool


class GitDiffError(Exception):
    """
    `git diff` command produced an error.
    """
    pass

class GitDiffReporter():
    """
    Query information from a Git diff between branches.
    """

    def __init__(self, diff_filepath=None):
        """
        Configure the reporter to use `git_diff` as the wrapper
        for the `git diff` tool.  (Should have same interface
        as `git_diff.GitDiffTool`)
        """
#         name = "{branch}...HEAD, staged, and unstaged changes".format(branch=compare_branch)
#         super(GitDiffReporter, self).__init__(name)

#         self._compare_branch = compare_branch
#         self._git_diff_tool = diff_filepath
#         self._ignore_unstaged = ignore_unstaged
        self._diff_filepath=diff_filepath

        # Cache diff information as a dictionary
        # with file path keys and line number list values
        self._diff_dict = None

    def clear_cache(self):
        """
        Reset the git diff result cache.
        """
        self._diff_dict = None

    def src_paths_changed(self):
        """
        See base class docstring.
        """

        # Get the diff dictionary
        diff_dict = self._git_diff()

        # Return the changed file paths (dict keys)
        # in alphabetical order
        return sorted(diff_dict.keys(), key=lambda x: x.lower())

    def lines_changed(self, src_path):
        """
        See base class docstring.
        """

        # Get the diff dictionary (cached)
        diff_dict = self._git_diff()

        # Look up the modified lines for the source file
        # If no lines modified, return an empty list
        return diff_dict.get(src_path, [])

    def _get_included_diff_results(self):
        """
        Return a list of stages to be included in the diff results.
        """
#         included = [self._git_diff_tool.diff_committed(self._compare_branch),
#                     self._git_diff_tool.diff_staged()]
#         if not self._ignore_unstaged:
#             included.append(self._git_diff_tool.diff_unstaged())

        
        included=[open(self._diff_filepath).read()]
#         print(included)
        return included

    def _git_diff(self):
        """
        Run `git diff` and returns a dict in which the keys
        are changed file paths and the values are lists of
        line numbers.

        Guarantees that each line number within a file
        is unique (no repeats) and in ascending order.

        Returns a cached result if called multiple times.

        Raises a GitDiffError if `git diff` has an error.
        """

        # If we do not have a cached result, execute `git diff`
        if self._diff_dict is None:

            result_dict = dict()

            for diff_str in self._get_included_diff_results():
                # Parse the output of the diff string
                diff_dict = self._parse_diff_str(diff_str)

                for src_path in diff_dict.keys():
                    added_lines, deleted_lines = diff_dict[src_path]

                    # Remove any lines from the dict that have been deleted
                    # Include any lines that have been added
                    result_dict[src_path] = [
                        line for line in result_dict.get(src_path, [])
                        if not line in deleted_lines
                    ] + added_lines

            # Eliminate repeats and order line numbers
            for (src_path, lines) in result_dict.items():
                result_dict[src_path] = self._unique_ordered_lines(lines)

            # Store the resulting dict
            self._diff_dict = result_dict

        # Return the diff cache
        return self._diff_dict

    # Regular expressions used to parse the diff output
    SRC_FILE_RE = re.compile(r'^diff --git "?a/.*"? "?b/([^ \n"]*)"?')
    MERGE_CONFLICT_RE = re.compile(r'^diff --cc ([^ \n]*)')
    HUNK_LINE_RE = re.compile(r'\+([0-9]*)')

    def _parse_diff_str(self, diff_str):
        """
        Parse the output of `git diff` into a dictionary of the form:

            { SRC_PATH: (ADDED_LINES, DELETED_LINES) }

        where `ADDED_LINES` and `DELETED_LINES` are lists of line
        numbers added/deleted respectively.

        If the output could not be parsed, raises a GitDiffError.
        """

        # Create a dict to hold results
        diff_dict = dict()

        # Parse the diff string into sections by source file
        sections_dict = self._parse_source_sections(diff_str)
        for (src_path, diff_lines) in sections_dict.items():

            # Parse the hunk information for the source file
            # to determine lines changed for the source file
            diff_dict[src_path] = self._parse_lines(diff_lines)

        return diff_dict

    def _parse_source_sections(self, diff_str):
        """
        Given the output of `git diff`, return a dictionary
        with keys that are source file paths.

        Each value is a list of lines from the `git diff` output
        related to the source file.

        Raises a `GitDiffError` if `diff_str` is in an invalid format.
        """

        # Create a dict to map source files to lines in the diff output
        source_dict = dict()

        # Keep track of the current source file
        src_path = None

        # Signal that we've found a hunk (after starting a source file)
        found_hunk = False

        # Parse the diff string into sections by source file
        for line in diff_str.split('\n'):

            # If the line starts with "diff --git"
            # or "diff --cc" (in the case of a merge conflict)
            # then it is the start of a new source file
            if line.startswith('diff --git') or line.startswith('diff --cc'):

                # Retrieve the name of the source file
                src_path = self._parse_source_line(line)

                # Create an entry for the source file, if we don't
                # already have one.
                if src_path not in source_dict:
                    source_dict[src_path] = []

                # Signal that we're waiting for a hunk for this source file
                found_hunk = False

            # Every other line is stored in the dictionary for this source file
            # once we find a hunk section
            else:

                # Only add lines if we're in a hunk section
                # (ignore index and files changed lines)
                if found_hunk or line.startswith('@@'):

                    # Remember that we found a hunk
                    found_hunk = True

                    if src_path is not None:
                        source_dict[src_path].append(line)

                    else:
                        # We tolerate other information before we have
                        # a source file defined, unless it's a hunk line
                        if line.startswith("@@"):
                            msg = "Hunk has no source file: '{0}'".format(line)
                            raise GitDiffError(msg)

        return source_dict

    def _parse_lines(self, diff_lines):
        """
        Given the diff lines output from `git diff` for a particular
        source file, return a tuple of `(ADDED_LINES, DELETED_LINES)`

        where `ADDED_LINES` and `DELETED_LINES` are lists of line
        numbers added/deleted respectively.

        Raises a `GitDiffError` if the diff lines are in an invalid format.
        """

        added_lines = []
        deleted_lines = []

        current_line_new = None
        current_line_old = None

        for line in diff_lines:

            # If this is the start of the hunk definition, retrieve
            # the starting line number
            if line.startswith('@@'):
                line_num = self._parse_hunk_line(line)
                current_line_new, current_line_old = line_num, line_num

            # This is an added/modified line, so store the line number
            elif line.startswith('+'):

                # Since we parse for source file sections before
                # calling this method, we're guaranteed to have a source
                # file specified.  We check anyway just to be safe.
                if current_line_new is not None:

                    # Store the added line
                    added_lines.append(current_line_new)

                    # Increment the line number in the file
                    current_line_new += 1

            # This is a deleted line that does not exist in the final
            # version, so skip it
            elif line.startswith('-'):

                # Since we parse for source file sections before
                # calling this method, we're guaranteed to have a source
                # file specified.  We check anyway just to be safe.
                if current_line_old is not None:

                    # Store the deleted line
                    deleted_lines.append(current_line_old)

                    # Increment the line number in the file
                    current_line_old += 1

            # This is a line in the final version that was not modified.
            # Increment the line number, but do not store this as a changed
            # line.
            else:
                if current_line_old is not None:
                    current_line_old += 1

                if current_line_new is not None:
                    current_line_new += 1

                # If we are not in a hunk, then ignore the line
                else:
                    pass

        return added_lines, deleted_lines

    def _parse_source_line(self, line):
        """
        Given a source line in `git diff` output, return the path
        to the source file.
        """
        if '--git' in line:
            regex = self.SRC_FILE_RE
        elif '--cc' in line:
            regex = self.MERGE_CONFLICT_RE
        else:
            msg = "Do not recognize format of source in line '{0}'".format(line)
            raise GitDiffError(msg)

        # Parse for the source file path
        groups = regex.findall(line)

        if len(groups) == 1:
            return groups[0]

        else:
            msg = "Could not parse source path in line '{0}'".format(line)
            raise GitDiffError(msg)

    def _parse_hunk_line(self, line):
        """
        Given a hunk line in `git diff` output, return the line number
        at the start of the hunk.  A hunk is a segment of code that
        contains changes.

        The format of the hunk line is:

            @@ -k,l +n,m @@ TEXT

        where `k,l` represent the start line and length before the changes
        and `n,m` represent the start line and length after the changes.

        `git diff` will sometimes put a code excerpt from within the hunk
        in the `TEXT` section of the line.
        """
        # Split the line at the @@ terminators (start and end of the line)
        components = line.split('@@')

        # The first component should be an empty string, because
        # the line starts with '@@'.  The second component should
        # be the hunk information, and any additional components
        # are excerpts from the code.
        if len(components) >= 2:

            hunk_info = components[1]
            groups = self.HUNK_LINE_RE.findall(hunk_info)

            if len(groups) == 1:

                try:
                    return int(groups[0])

                except ValueError:
                    msg = "Could not parse '{0}' as a line number".format(groups[0])
                    raise GitDiffError(msg)

            else:
                msg = "Could not find start of hunk in line '{0}'".format(line)
                raise GitDiffError(msg)

        else:
            msg = "Could not parse hunk in line '{0}'".format(line)
            raise GitDiffError(msg)

    @staticmethod
    def _unique_ordered_lines(line_numbers):
        """
        Given a list of line numbers, return a list in which each line
        number is included once and the lines are ordered sequentially.
        """

        if len(line_numbers) == 0:
            return []

        # Ensure lines are unique by putting them in a set
        line_set = set(line_numbers)

        # Retrieve the list from the set, sort it, and return
        return sorted([line for line in line_set])

"""
compare the git diff and jacoco result
generate the report of which java file changed, and how many lines be covered on new code.
"""
def report(diff_report, jacoco_html_report_path):
#     diff_report={u'pom.xml': [188, 189, 190, 191, 192, 193, 194, 195, 196, 197, 198, 199, 200, 201, 202, 203, 311, 312, 313, 314, 315, 316, 317, 318, 319, 320, 321, 322, 323, 324, 325, 326, 327, 328, 329, 330, 331, 332, 333, 334, 335, 336, 337, 338, 339, 340, 341], u'src/main/java/com/zuora/event/transformer/TransformerApplication.java': [22, 23, 24, 25, 26, 27, 28, 29, 30, 32, 33, 34, 35, 36, 37, 38, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49]}
#     jacoco_report_path="/Users/mli/work/git/sonarbitbucket/target/site/jacoco/"
    report={}
    for key in diff_report.keys():
        print("In parsing...->"+key)
        if key.endswith(".java"):
            javaname=re.search("(\w*)\.java",key).group();
            path=re.search("com/(.*)/", key).group();
            path=path.replace("/",".")[:-1]
            link=path+"/"+javaname+".html"
            jacoco_file_path=jacoco_html_report_path+link
#             print(javaname, jacoco_file_path)
            try:
                tree = ET.parse(jacoco_file_path)
            except ET.ParseError as err:
                print(err)
                report[path+javaname]={'link':0,'nc':0,'pc':0,'fc':0,'new':0}
                continue
                
            xmlns = {'html': '{http://www.w3.org/1999/xhtml}'}
            root = tree.getroot()
            nc=0
            fc=0
            pc=0
            new=0
            for line_num in diff_report[key]:
                find=".//{html}span[@id=\"L"+str(line_num)+"\"]"
                find=find.format(**xmlns)
#                 print(find)
                line=root.find(find)
                if line is None:
#                     print('can not find'+find)
                    pass
                if line is not None:
                    new+=1
                    covered=line.get("class")
                    if covered == 'nc':
                        nc+=1
                    if covered == 'pc':
                        pc+=1
                    if covered == 'fc':
                        fc+=1
#                     print(line.get('id'),covered)
            report[path+javaname]={'link':link,'nc':nc,'pc':pc,'fc':fc,'new':new}
#     print(report)        
    return report

"""
covert the report to a html file, more friendly to user than a pain txt
"""
def generateHtml(report, jacoco_html_path):
    """
    Prepare the data for generate HTML.
    """
    global id_a,id_b,id_c,id_d,id_e,id_f,id_g,id_h,id_i,id_j    
    id_a = []
    id_b = []
    id_c = []
    id_d = []
    id_e = []
    id_f = []
    id_g = []
    id_h = []
    id_i = []
    id_j = []
    global total_new,total_nc,total_pc,total_fc
    total_new=0
    total_nc=0
    total_pc=0
    total_fc=0
    for key in report:
        total_new+=report[key]['new']
        total_nc+=report[key]['nc']
        total_pc+=report[key]['pc']
        total_fc+=report[key]['fc']
    for key in report:
        id_a.append(key)
        id_b.append(report[key]['new'])
        id_c.append(report[key]['new']-report[key]['nc'])
        id_d.append((report[key]['new']-report[key]['nc'])/float(report[key]['new']) if report[key]['new'] else 0)
        id_e.append(report[key]['nc'])
        id_f.append(report[key]['nc']/float(report[key]['new']) if report[key]['new'] else 0)
        id_g.append(report[key]['pc'])
        id_h.append(report[key]['pc']/float(report[key]['new']) if report[key]['new'] else 0)
        id_i.append(report[key]['fc'])
        id_j.append(report[key]['fc']/float(report[key]['new']) if report[key]['new'] else 0)

    id_a.sort()
    id_b.sort()
    id_c.sort()
    id_d.sort()
    id_e.sort()
    id_f.sort()
    id_g.sort()
    id_h.sort()
    id_i.sort()
    id_j.sort()

    html='<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">'
    html=html+'<html><head><meta http-equiv="Content-Type" content="text/html;charset=UTF-8" />\
        <link rel="stylesheet" href=".resources/report.css" type="text/css" />\
        <link rel="shortcut icon" href=".resources/report.gif" type="image/gif" />\
        <title>code coverage</title><script type="text/javascript" src=".resources/sort.js"></script>\
        </head><body onload="initialSort([{0}])">'.format("'coveragetable'")+\
        '<div class="breadcrumb" id="breadcrumb"><span class="el_report">code coverage report</span></div><h1>Code Coverage on New Code Report</h1>'
    table='<table class="coverage" cellspacing="0" id="coveragetable">'
    table=table+'<thead><tr><td class="sortable" id="a" onclick="toggleSort(this)">File Name</td>\
                 <td class="sortable" id="b" onclick="toggleSort(this)">New Lines</td>\
                 <td class="sortable ctr1" id="c" onclick="toggleSort(this)">Covered</td>\
                 <td class="sortable ctr2" id="d" onclick="toggleSort(this)">Cov.</td>\
                 <td class="sortable ctr1" id="e" onclick="toggleSort(this)">No Covered</td>\
                 <td class="sortable ctr2" id="f" onclick="toggleSort(this)">Cov.</td>\
                 <td class="sortable ctr1" id="g" onclick="toggleSort(this)">Partical Covered</td>\
                 <td class="sortable ctr2" id="h" onclick="toggleSort(this)">Cov.</td>\
                 <td class="sortable ctr1" id="i" onclick="toggleSort(this)">Full Covered</td>\
                 <td class="sortable ctr2" id="j" onclick="toggleSort(this)">Cov.</td></tr></thead>'            
 
    for key in report:            
        table=table+'<tr><td id="a{0}">'.format(id_a.index(key))+\
        '<a href="'+str(report[key]['link'])+'"class="el_package">'+key+\
        '</a></td><td id="b{0}">'.format(id_b.index(report[key]['new']))+str(report[key]['new'])+\
        '</td><td class="bar" id="c{0}">'.format(id_c.index(report[key]['new']-report[key]['nc']))+'<img src=".resources/greenbar.gif" width="'+str((report[key]['fc']+report[key]['pc'])/float(report[key]['new'])*100 if report[key]['new'] else 0)+\
        '" height="10" title="'+str(report[key]['new']-report[key]['nc'])+'" alt="'+str(report[key]['new']-report[key]['nc'])+\
        '"/><img src=".resources/redbar.gif" width="'+str((report[key]['nc'])/float(report[key]['new'])*100 if report[key]['new'] else 0)+\
        '" height="10" title="'+str(report[key]['nc'])+'" alt="'+str(report[key]['nc'])+'"/>'\
        '</td><td class="ctr2" id="d{0}">'.format(id_d.index((report[key]['new']-report[key]['nc'])/float(report[key]['new']) if report[key]['new'] else 0))+'{percent:.2%}'.format(percent=(report[key]['new']-report[key]['nc'])/float(report[key]['new']) if report[key]['new'] else 0)+\
        '</td><td class="ctr1" id="e{0}">'.format(id_e.index(report[key]['nc']))+str(report[key]['nc'])+\
        '</td><td class="ctr2" id="f{0}">'.format(id_f.index(report[key]['nc']/float(report[key]['new']) if report[key]['new'] else 0))+'{percent:.2%}'.format(percent=report[key]['nc']/float(report[key]['new']) if report[key]['new'] else 0)+\
        '</td><td class="ctr1" id="g{0}">'.format(id_g.index(report[key]['pc']))+str(report[key]['pc'])+\
        '</td><td class="ctr2" id="h{0}">'.format(id_h.index(report[key]['pc']/float(report[key]['new'])) if report[key]['new'] else 0)+'{percent:.2%}'.format(percent=report[key]['pc']/float(report[key]['new']) if report[key]['new'] else 0)+\
        '</td><td class="ctr1" id="i{0}">'.format(id_i.index(report[key]['fc']))+str(report[key]['fc'])+\
        '</td><td class="ctr2" id="j{0}">'.format(id_j.index(report[key]['fc']/float(report[key]['new']) if report[key]['new'] else 0))+\
        '{percent:.2%}'.format(percent=report[key]['fc']/float(report[key]['new']) if report[key]['new'] else 0)+\
        '</td></tr>'
    table=table+'<tfoot><tr><td>'+' Total'+'</td><td>'+str(total_new)+\
    '</td><td class="bar"><img  src=".resources/greenbar.gif" width="'+str(float(total_fc+total_pc)/float(total_new)*100 if total_new else 0)+\
    '" height="10" title="'+str(total_fc+total_pc)+'" alt="'+str(total_fc+total_pc)+\
    '"/><img src=".resources/redbar.gif" width="'+str(float(total_nc)/float(total_new)*100 if total_new else 0)+\
    '" height="10" title="'+str(total_nc)+'" alt="'+str(total_nc)+'"/>'\
    '</td><td class="ctr2">'+'{percent:.2%}'.format(percent=((total_fc+total_pc)/float(total_new) if total_new else 0))+\
    '</td><td class="ctr1">'+str(total_nc)+'</td><td class="ctr2">'+'{percent:.2%}'.format(percent=total_nc/float(total_new) if total_new else 0)+\
    '</td><td class="ctr1">'+str(total_pc)+'</td><td class="ctr2">'+'{percent:.2%}'.format(percent=total_pc/float(total_new) if total_new else 0)+\
    '</td><td class="ctr1">'+str(total_fc)+'</td><td class="ctr2">'+'{percent:.2%}'.format(percent=total_fc/float(total_new) if total_new else 0)+\
    '</td></tr></tfoot></table>'            
    html=html+table
    html=html+'<div class="footer"><span class="right">Zuora Code Coverage Report</span></div>'
    html=html+'</body></html>'   
    with open(jacoco_html_path+"/coverageOnNewCode.html", 'w') as file:
       file.write(html)
    if total_new > 0 :   
        return '{percent:.2%}'.format(percent=(total_new-total_nc)/float(total_new))
    else:
        return '100%'

def toHtml(report, jacoco_html_path):
    html='<html><body><table>'
    table='<tr><th>file name</th><th>new lines</th><th>no covered</th><th>partical covered</th><th>full covered</th><th>link</th></tr>'
    total_new=0
    total_nc=0
    total_pc=0
    total_fc=0
    for key in report:
        total_new+=report[key]['new']
        total_nc+=report[key]['nc']
        total_pc+=report[key]['pc']
        total_fc+=report[key]['fc']
        table=table+'<tr><td>'+key+'</td><td>'+str(report[key]['new'])+'</td><td>'+str(report[key]['nc'])+'</td><td>'+str(report[key]['pc'])+'</td><td>'+str(report[key]['fc'])+'</td><td><a href="'+str(report[key]['link'])+'">link</a></td></tr>'
    table=table+'</table>'
    total_coverage='{percent:.2%}'.format(percent=(total_new-total_nc)/float(total_new))
    html=html+'<h3><p>total new lines:'+str(total_new)+'</p><p>         miss covered lines:'+str(total_nc)+' </p><p>        coverage on new code:'+total_coverage +'</p></h3>'
    html=html+table
    html=html+'</body></html>'
    with open(jacoco_html_path+"newcodecoverage.html", 'w') as file:
        file.write(html)
    return total_coverage
    
"""
main function
"""    
def jacoco_on_new_code(gitdiff_file='/Users/mli/work/git/test/gitdiff.txt',jacoco_html_path='/Users/mli/work/git/test/target/site/jacoco/'):
    gdr=GitDiffReporter(gitdiff_file)
    cc_report=report(gdr._git_diff(), jacoco_html_path)
    total_coverage=(generateHtml(cc_report,jacoco_html_path))
    print(total_coverage)
    return total_coverage

    
if __name__ == '__main__':
    arguments = sys.argv
    if len(arguments) == 3:
        jacoco_on_new_code(arguments[1],arguments[2])
    else:
        print('usage:')
        print('python '+arguments[0]+' gitdiff_file jacoco_html_path')
        print('e.g.')
        print('python '+arguments[0]+' /Users/mli/work/git/test/gitdiff.txt /Users/mli/work/git/test/target/site/jacoco/')
            


